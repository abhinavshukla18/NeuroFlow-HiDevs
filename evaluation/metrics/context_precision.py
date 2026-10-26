import asyncio

from evaluation.metrics import ask, content_tokens, strip_citations

PROMPT = (
    "Query: {query}\n\nAnswer: {answer}\n\nPassage: {chunk}\n\n"
    "Was this passage useful in generating the answer? Answer with exactly one word: yes or no."
)
FALLBACK_OVERLAP = 0.25


def _heuristic_useful(chunk: str, answer: str) -> bool:
    chunk_words = content_tokens(chunk)
    if not chunk_words:
        return False
    return len(chunk_words & content_tokens(answer)) / len(chunk_words) >= FALLBACK_OVERLAP


async def evaluate_context_precision(query: str, chunks: list[str], answer: str, client=None) -> float:
    if not chunks:
        return 0.0
    answer = strip_citations(answer or "")

    async def useful(chunk: str) -> bool:
        verdict = await ask(PROMPT.format(query=query, answer=answer, chunk=chunk), client)
        if verdict is None:
            return _heuristic_useful(chunk, answer)
        return verdict.strip().lower().startswith("yes")

    flags = await asyncio.gather(*(useful(c) for c in chunks))
    weights = [1 / rank for rank in range(1, len(chunks) + 1)]
    return sum(w for w, f in zip(weights, flags) if f) / sum(weights)