import uuid
import json

from fastapi import APIRouter, HTTPException

from db.pool import get_pool

router = APIRouter()


@router.get("/documents/{document_id}/chunks")
async def document_chunks(document_id: uuid.UUID):
    rows = await get_pool().fetch(
        "SELECT id, chunk_index, content, token_count FROM chunks "
        "WHERE document_id = $1 ORDER BY chunk_index",
        document_id,
    )
    return [
        {
            "id": str(r["id"]),
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "token_count": r["token_count"],
        }
        for r in rows
    ]


@router.get("/chunks/{chunk_id}/similar")
async def similar_chunks(chunk_id: uuid.UUID, limit: int = 8):
    pool = get_pool()
    if not await pool.fetchval("SELECT 1 FROM chunks WHERE id = $1 AND embedding IS NOT NULL", chunk_id):
        raise HTTPException(404, "Chunk not found or has no embedding")
    rows = await pool.fetch(
        "SELECT c.id, c.document_id, c.chunk_index, c.content, d.filename, "
        "1 - (c.embedding <=> (SELECT embedding FROM chunks WHERE id = $1)) AS similarity "
        "FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.id <> $1 AND c.embedding IS NOT NULL "
        "ORDER BY c.embedding <=> (SELECT embedding FROM chunks WHERE id = $1) LIMIT $2",
        chunk_id, limit,
    )
    return [
        {
            "id": str(r["id"]),
            "document_id": str(r["document_id"]),
            "filename": r["filename"],
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "similarity": round(float(r["similarity"]), 3),
        }
        for r in rows
    ]

@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: uuid.UUID):
    r = await get_pool().fetchrow(
        "SELECT c.id, c.content, c.chunk_index, c.token_count, c.metadata, "
        "d.id AS document_id, d.filename, d.source_type, d.created_at "
        "FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = $1",
        chunk_id,
    )
    if r is None:
        raise HTTPException(404, "Chunk not found")
    meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
    return {
        "id": str(r["id"]),
        "content": r["content"],
        "chunk_index": r["chunk_index"],
        "token_count": r["token_count"],
        "metadata": meta,
        "document": {
            "id": str(r["document_id"]),
            "filename": r["filename"],
            "source_type": r["source_type"],
            "created_at": r["created_at"].isoformat(),
        },
    }