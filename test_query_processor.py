import asyncio

from pipelines.retrieval.query_processor import classify_query, extract_filters, process_query

f = extract_filters("Show me documents from 2023 about climate change")
print(f)
assert f == {"year": 2023, "topic": "climate"}

assert classify_query("What is HNSW indexing?") == "factual"
assert classify_query("Why did sales drop in 2023?") == "analytical"
assert classify_query("Compare HNSW vs IVFFlat") == "comparative"
assert classify_query("How to install pgvector") == "procedural"

analysis = asyncio.run(process_query("Show me documents from 2023 about climate change"))
print(analysis)
assert analysis.all_queries == ["Show me documents from 2023 about climate change"]
print("PASS")