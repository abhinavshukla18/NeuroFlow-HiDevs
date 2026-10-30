from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from pipelines.ingestion.extractors import ExtractedPage

USER_AGENT = "NeuroFlowBot/1.0"


class RobotsDisallowed(Exception):
    pass


async def _allowed(client: httpx.AsyncClient, url: str) -> bool:
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        response = await client.get(robots_url)
    except httpx.HTTPError:
        return True
    if response.status_code >= 500:
        return False
    if response.status_code >= 400:
        return True
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


async def extract_url(url: str, client: httpx.AsyncClient | None = None) -> list[ExtractedPage]:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
        )
    try:
        if not await _allowed(client, url):
            raise RobotsDisallowed(f"robots.txt disallows fetching {url}")
        response = await client.get(url)
        response.raise_for_status()
        html = response.text
    finally:
        if own_client:
            await client.aclose()

    text = trafilatura.extract(html, url=url, include_tables=True)
    if not text:
        return []

    meta = trafilatura.extract_metadata(html, default_url=url)
    metadata = {
        "title": getattr(meta, "title", None),
        "author": getattr(meta, "author", None),
        "canonical_url": getattr(meta, "url", None) or url,
        "publish_date": getattr(meta, "date", None),
        "source_url": url,
    }
    return [ExtractedPage(1, text, "text", metadata)]