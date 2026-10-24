import asyncio

import httpx

from pipelines.ingestion.extractors.url_extractor import RobotsDisallowed, extract_url

PAGE = """<html><head><title>NeuroFlow Guide</title>
<meta name="author" content="Asha">
<link rel="canonical" href="https://example.com/article">
<meta property="article:published_time" content="2026-10-01"></head>
<body><nav>Home | About</nav><article><h1>NeuroFlow Guide</h1>
<p>NeuroFlow is a retrieval augmented generation platform that ingests many kinds of documents.</p>
<p>It extracts content, splits it into chunks, embeds them, and stores the vectors in Postgres.</p>
<p>Every answer is scored automatically for faithfulness and relevance, so quality can be tracked.</p>
<table><tr><th>Name</th><th>Score</th></tr><tr><td>Asha</td><td>92</td></tr></table>
</article><footer>Copyright</footer></body></html>"""


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /private")
    return httpx.Response(200, text=PAGE)


async def main():
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pages = await extract_url("https://example.com/article", client)
    print(pages[0].content_type, pages[0].metadata)
    print(pages[0].content)
    assert "retrieval augmented" in pages[0].content

    try:
        await extract_url("https://example.com/private/x", client)
        raise SystemExit("FAIL: robots.txt was not respected")
    except RobotsDisallowed as exc:
        print("PASS robots.txt respected:", exc)


asyncio.run(main())