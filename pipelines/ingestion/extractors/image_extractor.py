import base64
import io

import pytesseract
from PIL import Image

from pipelines.ingestion.extractors import ExtractedPage
from providers.base import ChatMessage
from providers.router import RoutingCriteria

MAX_SIDE = 1024
PROMPT = "Describe this image in detail: objects, layout, charts, diagrams and any visible text."


def _prepare(path: str) -> Image.Image:
    image = Image.open(path)
    image.load()
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))  # keeps aspect ratio; longest side <= 1024
    return image


def _vision_content(provider: str, b64: str) -> list:
    if provider == "anthropic":
        image = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}
    else:
        image = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    return [{"type": "text", "text": PROMPT}, image]


async def extract_image(path: str, client) -> list[ExtractedPage]:
    image = _prepare(path)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    b64 = base64.b64encode(buffer.getvalue()).decode()

    metadata = {"width": image.width, "height": image.height}

    criteria = RoutingCriteria(task_type="rag_generation", require_vision=True)
    cfg = await client.router.select(criteria)
    result = await client.chat([ChatMessage("user", _vision_content(cfg.provider, b64))], criteria)
    description = result.content.strip()
    metadata["vision_model"] = cfg.model

    try:
        ocr_text = pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError:
        ocr_text = ""
        metadata["ocr"] = "tesseract_not_installed"

    content = description + "\n\nText found in image: " + ocr_text
    return [ExtractedPage(1, content, "image_description", metadata)]