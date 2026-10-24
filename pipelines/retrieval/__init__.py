from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    chunk_id: str
    content: str
    score: float = 0.0
    document_id: str = ""
    source_name: str = ""
    page_number: int | None = None
    metadata: dict = field(default_factory=dict)
    strategies: list[str] = field(default_factory=list)