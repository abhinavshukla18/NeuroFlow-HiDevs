from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.fusion import reciprocal_rank_fusion


def r(cid, name):
    return RetrievalResult(chunk_id=cid, content=cid, strategies=[name])


dense = [r("A", "dense"), r("B", "dense"), r("C", "dense")]
sparse = [r("D", "sparse"), r("B", "sparse"), r("A", "sparse")]

fused = reciprocal_rank_fusion([dense, sparse])
ids = [x.chunk_id for x in fused]
print([(x.chunk_id, round(x.score, 4), x.strategies) for x in fused])

assert set(ids[:2]) == {"A", "B"}, "chunks in both lists must rank first"
assert abs(fused[0].score - (1 / 61 + 1 / 63)) < 1e-9 or abs(fused[0].score - (1 / 62 + 1 / 62)) < 1e-9
assert ids.index("A") < ids.index("C") and ids.index("B") < ids.index("D")
print("PASS: RRF boosts chunks that appear in multiple lists")