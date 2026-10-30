import asyncio

import numpy as np

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
CACHE_DIR = "/data/models"
TARGET_DIM = 1536  # matches the vector(1536) column; zero-padding keeps cosine distances unchanged

_embedder = None
_reranker = None


def _embed_sync(texts: list[str]) -> list[list[float]]:
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name=EMBED_MODEL, cache_dir=CACHE_DIR)
    vectors = []
    for v in _embedder.embed(texts):
        padded = np.zeros(TARGET_DIM, dtype=np.float32)
        padded[: len(v)] = v
        vectors.append(padded.tolist())
    return vectors


def _rerank_sync(query: str, passages: list[str]) -> list[float]:
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _reranker = TextCrossEncoder(model_name=RERANK_MODEL, cache_dir=CACHE_DIR)
    return [float(s) for s in _reranker.rerank(query, passages)]


async def local_embed(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(_embed_sync, texts)


async def local_rerank(query: str, passages: list[str]) -> list[float]:
    return await asyncio.to_thread(_rerank_sync, query, passages)