from config import get_settings
from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.context_assembler import DEFAULT_TOKEN_BUDGET, assemble_context
from pipelines.retrieval.query_processor import process_query
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.retriever import Retriever, default_embed


class RetrievalPipeline:
    def __init__(self, client=None, embed=default_embed, reranker_mode: str = "api"):
        self.client = client
        self.retriever = Retriever(embed)
        self.reranker = Reranker(client, reranker_mode)

    @classmethod
    def from_settings(cls, reranker_mode: str = "api") -> "RetrievalPipeline":
        settings = get_settings()
        client = None
        if settings.openai_api_key or settings.anthropic_api_key:
            from providers.client import get_client
            client = get_client()
        if settings.local_models:
            reranker_mode = "local"
        return cls(client=client, reranker_mode=reranker_mode)

    async def _search(self, query: str, per_strategy: int, retrieval=None):
        analysis = await process_query(query, self.client)
        dense_k = sparse_k = per_strategy
        if retrieval is not None:
            dense_k, sparse_k = retrieval.dense_k, retrieval.sparse_k
            if not retrieval.query_expansion:
                analysis.expansions = []
            if not retrieval.metadata_filters_enabled:
                analysis.filters = {}
        fused = await self.retriever.retrieve(analysis, k=per_strategy, dense_k=dense_k, sparse_k=sparse_k)
        return analysis, fused

    async def retrieve(
        self, query: str, k: int = 10, rerank: bool = True, per_strategy: int = 20
    ) -> list[RetrievalResult]:
        _, fused = await self._search(query, per_strategy)
        if not rerank:
            return fused[:k]
        return await self.reranker.rerank(query, fused, top_k=k)

    async def run(self, query: str, k: int = 10, token_budget: int = DEFAULT_TOKEN_BUDGET, retrieval=None) -> dict:
        analysis, fused = await self._search(query, 20, retrieval)
        if retrieval is not None and retrieval.reranker == "none":
            results = fused[:k]
        else:
            results = await self.reranker.rerank(query, fused, top_k=k)
        return {
            "query_type": analysis.query_type,
            "filters": analysis.filters,
            "queries": analysis.all_queries,
            "results": results,
            "context": assemble_context(results, token_budget),
        }