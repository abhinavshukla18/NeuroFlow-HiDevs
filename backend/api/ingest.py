import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request

from db.pool import get_pool

router = APIRouter()

UPLOAD_DIR = Path("/data/uploads")
MAX_BYTES = 100 * 1024 * 1024
READ_CHUNK = 1024 * 1024
EXT_TO_TYPE = {
    ".pdf": "pdf", ".docx": "docx", ".csv": "csv", ".txt": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
}


async def _save_upload(upload, temp_path: Path) -> str:
    sha = hashlib.sha256()
    size = 0
    try:
        with open(temp_path, "wb") as out:
            while chunk := await upload.read(READ_CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File exceeds the 100MB limit")
                sha.update(chunk)
                out.write(chunk)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return sha.hexdigest()


@router.post("/ingest")
async def ingest(request: Request):
    document_id = uuid.uuid4()
    content_type = request.headers.get("content-type", "")
    temp_path: Path | None = None

    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Request body must be valid JSON")
        url = (body or {}).get("url", "")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(400, "A valid http(s) 'url' is required")
        source_type, filename, file_path = "url", url, url
        content_hash = hashlib.sha256(url.encode()).hexdigest()
        metadata = {"url": url}
    elif content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, "Field 'file' is required")
        filename = Path(upload.filename or "upload").name
        ext = Path(filename).suffix.lower()
        source_type = EXT_TO_TYPE.get(ext)
        if source_type is None:
            raise HTTPException(415, f"Unsupported file type '{ext}'. Allowed: {sorted(EXT_TO_TYPE)}")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = UPLOAD_DIR / f"tmp-{document_id}"
        content_hash = await _save_upload(upload, temp_path)
        file_path = str(UPLOAD_DIR / f"{document_id}{ext}")
        metadata = {"original_filename": filename}
    else:
        raise HTTPException(400, "Send multipart/form-data with 'file' or JSON with 'url'")

    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO documents (id, filename, source_type, content_hash, metadata, status) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, 'queued') "
            "ON CONFLICT (content_hash) DO NOTHING RETURNING id",
            document_id, filename, source_type, content_hash, json.dumps(metadata),
        )
        if row is None:
            existing = await conn.fetchrow(
                "SELECT id, status FROM documents WHERE content_hash = $1", content_hash
            )
            if temp_path:
                temp_path.unlink(missing_ok=True)
            return {"document_id": str(existing["id"]), "status": existing["status"], "duplicate": True}

    if temp_path:
        temp_path.rename(file_path)

    await request.app.state.arq.enqueue_job("ingest_document", str(document_id), file_path, source_type)
    return {"document_id": str(document_id), "status": "queued", "duplicate": False}


@router.get("/documents/{document_id}")
async def get_document(document_id: uuid.UUID):
    row = await get_pool().fetchrow(
        "SELECT id, filename, source_type, status, chunk_count, metadata, created_at "
        "FROM documents WHERE id = $1",
        document_id,
    )
    if row is None:
        raise HTTPException(404, "Document not found")
    return {
        "document_id": str(row["id"]),
        "filename": row["filename"],
        "source_type": row["source_type"],
        "status": row["status"],
        "chunk_count": row["chunk_count"],
        "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
        "created_at": row["created_at"].isoformat(),
    }