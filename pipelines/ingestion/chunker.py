import re
from dataclasses import dataclass, field

import numpy as np
import tiktoken

from pipelines.ingestion.extractors import ExtractedPage

ENC = tiktoken.get_encoding("cl100k_base")
TARGET_TOKENS = 512
OVERLAP_TOKENS = 64
SEMANTIC_THRESHOLD = 0.7
PARENT_MAX_TOKENS = 2000
LONG_PDF_PAGES = 50


@dataclass
class Chunk:
    content: str
    token_count: int
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)


def count_tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p and p.strip()]


def _split_long(sentence: str, target: int) -> list[str]:
    ids = ENC.encode(sentence, disallowed_special=())
    return [ENC.decode(ids[i : i + target]) for i in range(0, len(ids), target)]


def fixed_size(text: str, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    sentences: list[str] = []
    for s in _sentences(text):
        sentences.extend(_split_long(s, target) if count_tokens(s) > target else [s])
    counted = [(s, count_tokens(s)) for s in sentences]

    chunks: list[str] = []
    current: list[tuple[str, int]] = []
    total = 0
    for sentence, n in counted:
        if current and total + n > target:
            chunks.append(" ".join(s for s, _ in current))
            carry: list[tuple[str, int]] = []
            carry_tokens = 0
            for prev, pn in reversed(current):
                if carry_tokens + pn > overlap:
                    break
                carry.insert(0, (prev, pn))
                carry_tokens += pn
            if carry_tokens + n > target:
                carry, carry_tokens = [], 0
            current, total = carry, carry_tokens
        current.append((sentence, n))
        total += n
    if current:
        chunks.append(" ".join(s for s, _ in current))
    return chunks


async def semantic(text: str, embed, target: int = TARGET_TOKENS, threshold: float = SEMANTIC_THRESHOLD) -> list[str]:
    sentences = _sentences(text)
    if len(sentences) < 2:
        return fixed_size(text, target)
    vectors = np.array(await embed(sentences), dtype=float)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.where(norms == 0, 1, norms)
    sims = (vectors[:-1] * vectors[1:]).sum(axis=1)

    groups: list[str] = []
    current = [sentences[0]]
    for sentence, sim in zip(sentences[1:], sims):
        if sim < threshold:
            groups.append(" ".join(current))
            current = []
        current.append(sentence)
    groups.append(" ".join(current))

    out: list[str] = []
    for group in groups:
        out.extend(fixed_size(group, target, 0) if count_tokens(group) > target else [group])
    return out


def _level(page: ExtractedPage) -> int:
    level = str(page.metadata.get("level", ""))
    return int(level[1:]) if level[:1] == "h" and level[1:].isdigit() else 0


def hierarchical(pages: list[ExtractedPage]) -> list[Chunk]:
    levels = [lvl for lvl in (_level(p) for p in pages) if lvl > 0]
    top = min(levels) if levels else 1

    sections: list[dict] = []
    for page in pages:
        if not sections or _level(page) == top:
            title = page.metadata.get("section", f"Section {len(sections) + 1}")
            sections.append({"title": title, "pages": []})
        sections[-1]["pages"].append(page)

    chunks: list[Chunk] = []
    for n, section in enumerate(sections):
        key = f"sec-{n}"
        ids = ENC.encode("\n\n".join(p.content for p in section["pages"]), disallowed_special=())[:PARENT_MAX_TOKENS]
        parent = Chunk(
            ENC.decode(ids), len(ids),
            metadata={"chunk_role": "parent", "section": section["title"], "section_key": key,
                      "child_count": 0, "strategy": "hierarchical"},
        )
        chunks.append(parent)
        for page in section["pages"]:
            for piece in fixed_size(page.content):
                chunks.append(Chunk(
                    piece, count_tokens(piece),
                    metadata={"chunk_role": "child", "parent_key": key,
                              "section": page.metadata.get("section", section["title"]),
                              "level": page.metadata.get("level"), "strategy": "hierarchical"},
                ))
                parent.metadata["child_count"] += 1
    return chunks


def select_strategy(source_type: str, content_type: str = "text", page_count: int = 1, has_headings: bool = False) -> str:
    if content_type == "table":
        return "fixed_size"
    if source_type == "docx" and has_headings:
        return "hierarchical"
    if source_type == "pdf" and page_count > LONG_PDF_PAGES:
        return "semantic"
    return "fixed_size"


async def chunk_document(pages: list[ExtractedPage], source_type: str, embed=None) -> list[Chunk]:
    page_count = max((p.page_number for p in pages), default=0)
    has_headings = any(_level(p) > 0 for p in pages)
    text_pages = [p for p in pages if p.content_type == "text"]
    other_pages = [p for p in pages if p.content_type != "text"]
    strategy = select_strategy(source_type, "text", page_count, has_headings)

    chunks: list[Chunk] = []
    if strategy == "hierarchical":
        chunks += hierarchical(text_pages)
    else:
        for page in text_pages:
            pieces = await semantic(page.content, embed) if strategy == "semantic" and embed else fixed_size(page.content)
            for piece in pieces:
                chunks.append(Chunk(piece, count_tokens(piece),
                                    metadata={**page.metadata, "page_number": page.page_number, "strategy": strategy}))
    for page in other_pages:
        for piece in fixed_size(page.content):
            chunks.append(Chunk(piece, count_tokens(piece),
                                metadata={**page.metadata, "page_number": page.page_number,
                                          "content_type": page.content_type, "strategy": "fixed_size"}))

    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
    return chunks