from dataclasses import replace

from pipelines.retrieval import RetrievalResult


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievalResult]], k: int = 60
) -> list[RetrievalResult]:
    scores: dict[str, float] = {}
    first_seen: dict[str, RetrievalResult] = {}
    strategies: dict[str, list[str]] = {}

    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(result.chunk_id, result)
            for name in result.strategies:
                if name not in strategies.setdefault(result.chunk_id, []):
                    strategies[result.chunk_id].append(name)

    fused = [
        replace(first_seen[cid], score=score, strategies=strategies.get(cid, []))
        for cid, score in scores.items()
    ]
    fused.sort(key=lambda r: r.score, reverse=True)
    return fused