import asyncio

from evaluation.metrics import ask, parse_json_list, split_sentences, strip_citations, support_ratio

CLAIMS_PROMPT = (
    "List every factual statement in the answer as a JSON array of strings. "
    "Return only the JSON array.\n\nAnswer: {answer}"
)
VERDICT_PROMPT = (
    "Context:\n{context}\n\nClaim: {claim}\n\n"
    "Is this claim supported by the context? Answer with exactly one word: yes, no, or partial."
)
REFUSAL_MARKERS = ("does not contain enough information", "cannot answer", "no relevant information")


def _is_refusal(answer: str) -> bool:
    return any(marker in answer.lower() for marker in REFUSAL_MARKERS)


def _verdict_to_score(text: str) -> float:
    word = (text or "").strip().lower()
    if word.startswith("yes"):
        return 1.0
    if word.startswith("partial"):
        return 0.5
    return 0.0


def _heuristic_score(claim: str, context: str) -> float:
    ratio = support_ratio(claim, context)
    return 1.0 if ratio >= 0.7 else 0.5 if ratio >= 0.4 else 0.0


async def evaluate_faithfulness(query: str, answer: str, context: str, client=None) -> float:
    answer = answer or ""
    if not context.strip():
        return 1.0 if _is_refusal(answer) else 0.0

    claims: list[str] = []
    raw = await ask(CLAIMS_PROMPT.format(answer=strip_citations(answer)), client)
    if raw:
        claims = parse_json_list(raw)
    if not claims:
        claims = split_sentences(answer)
    if not claims:
        return 0.0

    async def judge(claim: str) -> float:
        verdict = await ask(VERDICT_PROMPT.format(context=context, claim=claim), client)
        return _verdict_to_score(verdict) if verdict is not None else _heuristic_score(claim, context)

    scores = await asyncio.gather(*(judge(c) for c in claims))
    return sum(scores) / len(scores)