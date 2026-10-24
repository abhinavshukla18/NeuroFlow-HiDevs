from pipelines.ingestion.chunker import count_tokens
from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.context_assembler import assemble_context

results = [
    RetrievalResult(chunk_id=str(i), content=f"Sentence {i}. " * 60, source_name=f"doc{i % 2}.pdf", page_number=i + 1)
    for i in range(10)
]

for budget in (300, 1000, 4000):
    out = assemble_context(results, budget)
    actual = count_tokens(out.context)
    print(budget, "->", len(out.chunks_used), "chunks,", out.total_tokens, "tokens (recounted:", actual, ")")
    assert out.total_tokens <= budget and actual <= budget
    assert all(b["chunk_id"] for b in out.chunks_used)

out = assemble_context(results, 1000)
assert out.context.startswith("[Source 1 — doc0.pdf, page 1]")
assert out.context.rstrip().endswith("Sentence " + out.chunks_used[-1]["chunk_id"] + ".")
assert out.metadata["sources"] == ["doc0.pdf", "doc1.pdf"]
print("PASS budget respected, whole chunks only, metadata returned")