import json
import re
from dataclasses import dataclass, field

from config import get_settings
from providers.base import ChatMessage
from providers.router import RoutingCriteria

QUERY_TYPES = ("factual", "analytical", "comparative", "procedural")

PROMPT = """Analyze this search query. Reply with JSON only, no other text:
{{"expansions": [2 or 3 alternative phrasings of the query],
 "filters": {{optional metadata filters such as "year" (integer) and "topic" (one lowercase word); use {{}} if none are implied}},
 "query_type": one of "factual", "analytical", "comparative", "procedural"}}

Query: {query}"""


@dataclass
class QueryAnalysis:
    original: str
    expansions: list[str] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    query_type: str = "factual"

    @property
    def all_queries(self) -> list[str]:
        return [self.original] + [q for q in self.expansions if q and q != self.original]


def extract_filters(query: str) -> dict:
    filters: dict = {}
    year = re.search(r"\b(19|20)\d{2}\b", query)
    if year:
        filters["year"] = int(year.group())
    topic = re.search(r"\b(?:about|on|regarding)\s+(?:the\s+)?([a-zA-Z][a-zA-Z-]+)", query, re.IGNORECASE)
    if topic:
        filters["topic"] = topic.group(1).lower()
    return filters


def classify_query(query: str) -> str:
    q = query.lower()
    if re.search(r"\b(compare|versus|vs\.?|difference|differences|better than)\b", q):
        return "comparative"
    if re.search(r"\b(how (do|to|can|should)|steps?|procedure|process|guide|set up|install)\b", q):
        return "procedural"
    if re.search(r"\b(why|analy[sz]e|impact|implications?|evaluate|explain|trend)\b", q):
        return "analytical"
    return "factual"


def heuristic_analysis(query: str) -> QueryAnalysis:
    return QueryAnalysis(query, [], extract_filters(query), classify_query(query))


def _parse(query: str, text: str) -> QueryAnalysis:
    data = json.loads(text[text.index("{") : text.rindex("}") + 1])
    query_type = data.get("query_type", "")
    filters = data.get("filters") or {}
    return QueryAnalysis(
        original=query,
        expansions=[str(e) for e in (data.get("expansions") or [])][:3],
        filters=filters if isinstance(filters, dict) else {},
        query_type=query_type if query_type in QUERY_TYPES else classify_query(query),
    )


async def process_query(query: str, client=None) -> QueryAnalysis:
    settings = get_settings()
    if client is None or not (settings.openai_api_key or settings.anthropic_api_key):
        return heuristic_analysis(query)
    try:
        result = await client.chat(
            [ChatMessage("user", PROMPT.format(query=query))],
            RoutingCriteria(task_type="classification"),
        )
        return _parse(query, result.content)
    except Exception:
        return heuristic_analysis(query)