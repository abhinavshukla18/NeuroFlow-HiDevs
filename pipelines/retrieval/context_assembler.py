from dataclasses import dataclass, field

from pipelines.ingestion.chunker import count_tokens
from pipelines.retrieval import RetrievalResult

DEFAULT_TOKEN_BUDGET = 4000
SEPARATOR = "\n\n"


@dataclass
class AssembledContext:
    context: str
    chunks_used: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    sources: list[str] = field(default_factory=list)

    @property
    def metadata(self) -> dict:
        return {"chunks_used": self.chunks_used, "total_tokens": self.total_tokens, "sources": self.sources}


def _header(number: int, result: RetrievalResult) -> str:
    page = f", page {result.page_number}" if result.page_number else ""
    return f"[Source {number} — {result.source_name}{page}]"


def assemble_context(results: list[RetrievalResult], token_budget: int = DEFAULT_TOKEN_BUDGET) -> AssembledContext:
    blocks: list[str] = []
    used: list[dict] = []
    sources: list[str] = []
    total = 0

    for result in results:
        number = len(blocks) + 1
        block = f"{_header(number, result)}\n{result.content}"
        cost = count_tokens(block) + (count_tokens(SEPARATOR) if blocks else 0)
        if total + cost > token_budget:
            continue  # whole chunks only: never truncate mid-sentence
        blocks.append(block)
        total += cost
        used.append({
            "chunk_id": result.chunk_id,
            "document_id": result.document_id,
            "source_name": result.source_name,
            "page_number": result.page_number,
            "score": result.score,
            "content_preview": result.content[:100],
        })
        if result.source_name not in sources:
            sources.append(result.source_name)

    context = SEPARATOR.join(blocks)
    return AssembledContext(context, used, count_tokens(context), sources)
