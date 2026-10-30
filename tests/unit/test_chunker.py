import pytest

from pipelines.ingestion.chunker import (
    Chunk,
    chunk_document,
    count_tokens,
    fixed_size,
    select_strategy,
    semantic,
)
from pipelines.ingestion.extractors import ExtractedPage

LONG_TEXT = " ".join(f"This is sentence number {i} about retrieval systems." for i in range(200))


def test_count_tokens_positive():
    assert count_tokens("hello world") > 0


def test_count_tokens_grows_with_length():
    assert count_tokens(LONG_TEXT) > count_tokens("hello world")


def test_fixed_size_splits_long_text():
    chunks = fixed_size(LONG_TEXT, target=50, overlap=10)
    assert len(chunks) > 1
    assert all(isinstance(c, str) and c.strip() for c in chunks)


def test_fixed_size_short_text_is_single_chunk():
    chunks = fixed_size("Hello world.", target=50, overlap=10)
    assert len(chunks) == 1
    assert "Hello world" in chunks[0]


def test_fixed_size_covers_start_and_end():
    chunks = fixed_size(LONG_TEXT, target=50, overlap=10)
    assert "sentence number 0 " in chunks[0]
    assert "sentence number 199" in chunks[-1]


def test_fixed_size_overlap_never_reduces_chunk_count():
    with_overlap = fixed_size(LONG_TEXT, target=50, overlap=20)
    without = fixed_size(LONG_TEXT, target=50, overlap=0)
    assert len(with_overlap) >= len(without)


async def fake_embed(texts):
    return [[1.0, 0.0] if "cat" in t.lower() else [0.0, 1.0] for t in texts]


async def test_semantic_keeps_all_content():
    text = "Cats purr softly. Cats like milk. Stocks fell today. Markets dropped sharply."
    out = await semantic(text, fake_embed, target=200)
    joined = " ".join(out)
    assert out and all(isinstance(c, str) and c.strip() for c in out)
    assert "Cats purr softly" in joined
    assert "Markets dropped sharply" in joined


@pytest.mark.parametrize("source_type", ["pdf", "docx", "csv", "text", "image", "url"])
def test_select_strategy_returns_known_strategy(source_type):
    assert select_strategy(source_type) in {"fixed_size", "semantic", "hierarchical", "auto"}


async def test_chunk_document_returns_chunks():
    pages = [ExtractedPage(1, LONG_TEXT, "text", {})]
    chunks = await chunk_document(pages, "text")
    assert chunks
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(c.token_count > 0 for c in chunks)
    indexes = [c.chunk_index for c in chunks]
    assert len(set(indexes)) == len(indexes)