from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    document_id: str
    filename: str
    status: str
    chunk_count: int | None = None
    duplicate: bool = False


@dataclass
class QueryResult:
    run_id: str
    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvaluationResult:
    run_id: str
    faithfulness: float | None
    answer_relevance: float | None
    context_precision: float | None
    context_recall: float | None
    overall_score: float | None