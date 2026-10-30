import asyncio

from pipelines.ingestion.chunker import chunk_document, count_tokens, fixed_size, select_strategy, semantic
from pipelines.ingestion.extractors.docx_extractor import extract_docx

assert select_strategy("pdf", "text", 10) == "fixed_size"
assert select_strategy("pdf", "text", 60) == "semantic"
assert select_strategy("pdf", "table", 60) == "fixed_size"
assert select_strategy("docx", "text", 3, True) == "hierarchical"
assert select_strategy("csv", "table") == "fixed_size"
assert select_strategy("image", "image_description") == "fixed_size"
assert select_strategy("url", "text") == "fixed_size"
print("PASS strategy selection")

text = " ".join(f"Sentence number {i} talks about NeuroFlow ingestion pipelines." for i in range(400))
chunks = fixed_size(text)
assert len(chunks) > 1 and all(count_tokens(c) <= 512 for c in chunks)
assert chunks[0][-30:] in chunks[1]
print("PASS fixed_size:", len(chunks), "chunks, max", max(count_tokens(c) for c in chunks), "tokens, overlap present")


async def fake_embed(texts):
    return [[1.0, 0.0] if "cat" in t else [0.0, 1.0] for t in texts]


groups = asyncio.run(semantic(
    "The cat sat on the mat. The cat purred loudly. The stock market fell today. The stock index dropped again.",
    fake_embed))
assert len(groups) == 2
print("PASS semantic split:", groups)

pages = extract_docx("sample.docx")
result = asyncio.run(chunk_document(pages, "docx"))
roles = [(c.metadata.get("chunk_role"), c.metadata.get("section"), c.metadata["strategy"]) for c in result]
assert any(r[0] == "parent" for r in roles) and any(r[0] == "child" for r in roles)
print("PASS hierarchical:", roles)