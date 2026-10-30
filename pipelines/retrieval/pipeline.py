import time

from opentelemetry import trace

from config import get_settings
from monitoring.metrics import retrieval_latency
from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.context_assembler import DEFAULT_TOKEN_BUDGET, assemble_context
from pipelines.retrieval.query_processor import process_query
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.retriever import Retriever, default_embed

tracer = trace.get_tracer("neuroflow.retrieval")


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
        extra = {}
        if retrieval is not None:
            extra = {"ef_search": retrieval.ef_search, "rrf_k": retrieval.rrf_k}
        fused = await self.retriever.retrieve(
            analysis, k=per_strategy, dense_k=dense_k, sparse_k=sparse_k, **extra
        )
        return analysis, fused

    async def retrieve(
        self, query: str, k: int = 10, rerank: bool = True, per_strategy: int = 20
    ) -> list[RetrievalResult]:
        _, fused = await self._search(query, per_strategy)
        if not rerank:
            return fused[:k]
        return await self.reranker.rerank(query, fused, top_k=k)

    async def run(
        self,
        query: str,
        k: int = 10,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        retrieval=None,
        pipeline_id: str | None = None,
        run_id: str | None = None,
    ) -> dict:
        attrs = {"pipeline_id": pipeline_id or "", "run_id": run_id or ""}
        with tracer.start_as_current_span("retrieval.pipeline", attributes=attrs) as root:
            started = time.perf_counter()
            analysis, fused = await self._search(query, 20, retrieval)
            retrieval_latency.labels(strategy="search").observe(time.perf_counter() - started)

            with tracer.start_as_current_span("retrieval.rerank", attributes=attrs) as sp:
                t = time.perf_counter()
                if retrieval is not None and retrieval.reranker == "none":
                    results = fused[:k]
                else:
                    results = await self.reranker.rerank(query, fused, top_k=k)
                sp.set_attribute("chunk_count", len(results))
                retrieval_latency.labels(strategy="rerank").observe(time.perf_counter() - t)

            with tracer.start_as_current_span("retrieval.assemble", attributes=attrs) as sp:
                context = assemble_context(results, token_budget)
                sp.set_attribute("chunk_count", len(context.chunks_used))
                sp.set_attribute("token_count", len(context.context) // 4)

            root.set_attribute("chunk_count", len(results))
            retrieval_latency.labels(strategy="total").observe(time.perf_counter() - started)
            return {
                "query_type": analysis.query_type,
                "filters": analysis.filters,
                "queries": analysis.all_queries,
                "results": results,
                "context": context,
            }