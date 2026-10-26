import asyncio
import json

from config import get_settings
from db.pool import get_pool
from pipelines.ingestion.pipeline import _fake_vector
from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.fusion import reciprocal_rank_fusion
from pipelines.retrieval.query_processor import QueryAnalysis

COLUMNS = "c.id, c.content, c.document_id, c.metadata, d.filename"


async def default_embed(texts: list[str]) -> list[list[float]]:
    if get_settings().local_models:
        from pipelines.local_models import local_embed
        return await local_embed(texts)
    if get_settings().fake_embeddings:
        return [_fake_vector(t) for t in texts]
    from providers.client import get_client
    return await get_client().embed(texts)


def _vec(v: list[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


def _to_result(row, strategy: str, score: float) -> RetrievalResult:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return RetrievalResult(
        chunk_id=str(row["id"]),
        content=row["content"],
        score=score,
        document_id=str(row["document_id"]),
        source_name=row["filename"],
        page_number=metadata.get("page_number") or metadata.get("page"),
        metadata=metadata,
        strategies=[strategy],
    )


class Retriever:
    def __init__(self, embed=default_embed):
        self.embed = embed

    async def _dense_retrieval(self, queries: list[str], k: int) -> list[RetrievalResult]:
        vectors = await self.embed(queries)

        async def one(vector):
            rows = await get_pool().fetch(
                f"SELECT {COLUMNS}, c.embedding <=> $1::vector AS distance "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "ORDER BY c.embedding <=> $1::vector LIMIT $2",
                _vec(vector), k,
            )
            return [_to_result(r, "dense", 1.0 - float(r["distance"])) for r in rows]

        lists = await asyncio.gather(*(one(v) for v in vectors))
        return reciprocal_rank_fusion(list(lists))[:k] if len(lists) > 1 else lists[0]

    async def _sparse_retrieval(self, queries: list[str], k: int) -> list[RetrievalResult]:
        async def one(text):
            rows = await get_pool().fetch(
                f"SELECT {COLUMNS}, "
                "ts_rank_cd(to_tsvector('english', c.content), plainto_tsquery('english', $1)) AS rank "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', $1) "
                "ORDER BY rank DESC LIMIT $2",
                text, k,
            )
            return [_to_result(r, "sparse", float(r["rank"])) for r in rows]

        lists = await asyncio.gather(*(one(q) for q in queries))
        return reciprocal_rank_fusion(list(lists))[:k] if len(lists) > 1 else lists[0]

    async def _metadata_retrieval(self, query: str, filters: dict, k: int) -> list[RetrievalResult]:
        if not filters:
            return []
        (vector,) = await self.embed([query])
        rows = await get_pool().fetch(
            f"SELECT {COLUMNS}, c.embedding <=> $2::vector AS distance "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.metadata @> $1::jsonb ORDER BY c.embedding <=> $2::vector LIMIT $3",
            json.dumps(filters), _vec(vector), k,
        )
        return [_to_result(r, "metadata", 1.0 - float(r["distance"])) for r in rows]

    async def retrieve(self, analysis: QueryAnalysis, k: int = 20, dense_k: int | None = None,
                       sparse_k: int | None = None) -> list[RetrievalResult]:
        queries = analysis.all_queries
        results = await asyncio.gather(
            self._dense_retrieval(queries, dense_k or k),
            self._sparse_retrieval(queries, sparse_k or k),
            self._metadata_retrieval(analysis.original, analysis.filters, k),
        )
        return reciprocal_rank_fusion([r for r in results if r])