import ipaddress
import re
import socket
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import bleach
from fastapi import HTTPException

URL_RE = re.compile(r"^https?://", re.I)

ALLOWED_MIME = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".csv": {"text/csv", "application/vnd.ms-excel", "text/plain"},
    ".txt": {"text/plain"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
}


def clean_text(text: str) -> str:
    return bleach.clean(text, tags=[], strip=True)


def validate_url(url: str) -> str:
    if len(url) > 2048 or not URL_RE.match(url):
        raise HTTPException(400, "A valid http(s) URL is required")
    host = urlparse(url).hostname
    if not host or host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise HTTPException(400, "URL host is not allowed")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(400, "URL host could not be resolved")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise HTTPException(400, "URL points to a private or internal address")
    return url


def _sniff(path: Path, ext: str) -> bool:
    with open(path, "rb") as f:
        head = f.read(8192)
    if ext == ".pdf":
        return head.startswith(b"%PDF-")
    if ext == ".docx":
        if not head.startswith(b"PK\x03\x04") or not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as z:
            return "word/document.xml" in z.namelist()
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext in (".csv", ".txt"):
        if head.startswith((b"MZ", b"\x7fELF", b"#!")):
            return False
        return b"\x00" not in head
    return False


def validate_upload(content_type: str | None, ext: str, path: Path) -> None:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME.get(ext, set()):
        raise HTTPException(415, f"MIME type '{mime}' does not match '{ext}'")
    if not _sniff(path, ext):
        raise HTTPException(415, f"File content does not match '{ext}'")