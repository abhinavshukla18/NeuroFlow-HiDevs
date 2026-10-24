import uuid

from pipelines.generation.citations import parse_citations

ids = [str(uuid.uuid4()) for _ in range(3)]
chunks = [
    {"chunk_id": ids[i], "source_name": f"doc{i}.pdf", "page_number": i + 1, "content_preview": f"preview {i}"}
    for i in range(3)
]

text = "HNSW is a graph index [Source 1]. It is fast [Source 3][Source 1]. Also [Source 7] and [Source 0]."
cites = parse_citations(text, chunks)
print([c.to_dict() for c in cites])

assert [c.reference for c in cites] == ["Source 1", "Source 3", "Source 7", "Source 0"]
assert str(cites[0].chunk_id) == ids[0] and cites[0].document_name == "doc0.pdf" and cites[0].page_number == 1
assert str(cites[1].chunk_id) == ids[2] and cites[1].page_number == 3
assert cites[2].invalid_citation and cites[3].invalid_citation
assert not cites[0].invalid_citation and "invalid_citation" not in cites[0].to_dict()
assert parse_citations("No citations here.", chunks) == []
print("PASS")