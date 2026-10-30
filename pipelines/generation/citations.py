import re
from dataclasses import asdict, dataclass
from uuid import UUID

CITATION_RE = re.compile(r"\[Source\s+(\d+)\]", re.IGNORECASE)


@dataclass
class Citation:
    reference: str  # "Source 1"
    chunk_id: UUID | None
    document_name: str | None
    page_number: int | None
    content_preview: str | None
    invalid_citation: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["chunk_id"] = str(self.chunk_id) if self.chunk_id else None
        if not self.invalid_citation:
            data.pop("invalid_citation")
        return data


def parse_citations(response: str, chunks_used: list[dict]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[int] = set()
    for match in CITATION_RE.finditer(response):
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        reference = f"Source {number}"
        if 1 <= number <= len(chunks_used):
            chunk = chunks_used[number - 1]
            citations.append(Citation(
                reference=reference,
                chunk_id=UUID(chunk["chunk_id"]),
                document_name=chunk.get("source_name"),
                page_number=chunk.get("page_number"),
                content_preview=(chunk.get("content_preview") or "")[:100],
            ))
        else:
            citations.append(Citation(reference, None, None, None, None, invalid_citation=True))
    return citations