import json
import re

from config import get_settings
from providers.base import ChatMessage
from providers.router import RoutingCriteria

CITATION_RE = re.compile(r"\[Source\s+\d+\]", re.IGNORECASE)
STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from", "has", "have", "had",
    "its", "can", "not", "but", "all", "any", "into", "than", "then", "also", "which", "their", "there",
    "been", "being", "will", "would", "about", "what", "when", "how", "why", "who", "does", "did",
}


def llm_available() -> bool:
    settings = get_settings()
    return bool(settings.openai_api_key or settings.anthropic_api_key)


async def ask(prompt: str, client=None, temperature: float = 0.0) -> str | None:
    """Ask the judge LLM (always a capable, non-fine-tuned model). None means no LLM is available."""
    if client is None or not llm_available():
        return None
    result = await client.chat(
        [ChatMessage("user", prompt)],
        RoutingCriteria(task_type="evaluation"),
        temperature=temperature,
        max_tokens=800,
    )
    return result.content


def strip_citations(text: str) -> str:
    return CITATION_RE.sub("", text).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", strip_citations(text))
    return [p.strip() for p in parts if len(p.strip()) > 2]


def content_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def support_ratio(sentence: str, context: str) -> float:
    """Fallback judge: share of the sentence's content words that appear in the context."""
    words = content_tokens(sentence)
    if not words:
        return 1.0
    return len(words & content_tokens(context)) / len(words)


def parse_json_list(text: str) -> list[str]:
    try:
        data = json.loads(text[text.index("[") : text.rindex("]") + 1])
        return [str(item) for item in data if str(item).strip()]
    except (ValueError, TypeError):
        return []