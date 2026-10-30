import asyncio
from types import SimpleNamespace

from PIL import Image

from pipelines.ingestion.extractors.image_extractor import extract_image


class FakeRouter:
    async def select(self, criteria):
        assert criteria.require_vision is True
        return SimpleNamespace(provider="openai", model="fake-vision")


class FakeClient:
    router = FakeRouter()

    async def chat(self, messages, criteria):
        assert messages[0].content[1]["type"] == "image_url"
        return SimpleNamespace(content="A plain white rectangle.")


Image.new("RGB", (3000, 2000), "white").save("sample.png")
pages = asyncio.run(extract_image("sample.png", FakeClient()))
page = pages[0]
print(page.content_type, page.metadata)
print(page.content)
assert max(page.metadata["width"], page.metadata["height"]) == 1024