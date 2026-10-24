import asyncio
import hashlib
import json
import logging
import math
import random
import time

from opentelemetry import trace

from config import get_settings
from db.pool import get_pool
from pipelines.ingestion.chunker import chunk_document
from pipelines.ingestion.extractors import ExtractedPage
from pipelines.ingestion.extractors.csv_extractor import extract_csv
from pipelines.ingestion.extractors.docx_extractor import extract_docx
from pipelines.ingestion.extractors.image_extractor import extract_image
from pipelines.ingestion.extractors.pdf_extractor import extract_pdf
from pipelines.ingestion.extractors.url_extractor import extract_url

logger = logging.getLogger("neuroflow.ingestion")
tracer = trace.get_tracer("neuroflow.ingestion")

EMBED_BATCH = 100
EMBED_DIM = 1536


def _fake_vector(text: str) -> list[float]:
    rng = random.Random(hashlib.sha256(text.encode()).digest())
    vec = [rng.uniform(-1, 1) for _ in range(EMBED_DIM)]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


async def _extract(file_path: str, source_type: str) -> list[ExtractedPage]:
    if source_type == "pdf":
        return await asyncio.to_thread(extract_pdf, file_path)
    if source_type == "docx":
        return await asyncio.to_thread(extract_docx, file_path)
    if source_type == "csv":
        return await asyncio.to_thread(extract_csv, file_path)
    if source_type == "image":
        from providers.client import get_client
        return await extract_image(file_path, get_client())
    if source_type == "url":
        return await extract_url(file_path)
    if source_type == "text":
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return [ExtractedPage(1, f.read(), "text", {})]
    raise ValueError(f"Unsupported source_type: {source_type}")


async def process_document(document_id: str, file_path: str, source_type: str) -> dict:
    settings = get_settings()
    pool = get_pool()
    started = time.perf_counter()
    stats = {"embedding_calls": 0}

    async def embed(texts: list[str]) -> list[list[float]]:
        stats["embedding_calls"] += math.ceil(len(texts) / EMBED_BATCH)
        if settings.fake_embeddings:
            return [_fake_vector(t) for t in texts]
        from providers.client import get_client
        return await get_client().embed(texts)

    with tracer.start_as_current_span("ingestion.process") as span:
        span.set_attribute("document_id", document_id)
        span.set_attribute("source_type", source_type)
        try:
            await pool.execute("UPDATE documents SET status = 'processing' WHERE id = $1", document_id)

            pages = await _extract(file_path, source_type)
            span.set_attribute("page_count", len(pages))
            if not pages:
                raise ValueError("No content could be extracted")

            chunks = await chunk_document(pages, source_type, embed=embed)
            vectors: list[list[float]] = []
            for i in range(0, len(chunks), EMBED_BATCH):
                vectors.extend(await embed([c.content for c in chunks[i : i + EMBED_BATCH]]))

            rows = [
                (document_id, c.content, "[" + ",".join(map(str, v)) + "]",
                 c.chunk_index, c.token_count, json.dumps(c.metadata, default=str))
                for c, v in zip(chunks, vectors)
            ]
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM chunks WHERE document_id = $1", document_id)
                    await conn.executemany(
                        "INSERT INTO chunks (document_id, content, embedding, chunk_index, token_count, metadata) "
                        "VALUES ($1, $2, $3::vector, $4, $5, $6::jsonb)",
                        rows,
                    )
                    await conn.execute(
                        "UPDATE documents SET status = 'complete', chunk_count = $2 WHERE id = $1",
                        document_id, len(chunks),
                    )

            tokens = sum(c.token_count for c in chunks)
            duration_ms = round((time.perf_counter() - started) * 1000)
            span.set_attribute("chunk_count", len(chunks))
            span.set_attribute("embedding_calls", stats["embedding_calls"])
            logger.info(json.dumps({
                "event": "ingestion_complete", "document_id": document_id,
                "duration_ms": duration_ms, "chunks": len(chunks), "tokens": tokens,
            }))
            return {"document_id": document_id, "chunks": len(chunks)}

        except Exception as exc:
            logger.exception("Ingestion failed for %s", document_id)
            await pool.execute(
                "UPDATE documents SET status = 'failed', "
                "metadata = metadata || jsonb_build_object('error', $2::text) WHERE id = $1",
                document_id, str(exc)[:500],
            )
            span.record_exception(exc)
            return {"document_id": document_id, "error": str(exc)}