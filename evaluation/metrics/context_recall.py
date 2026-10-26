import asyncio

from evaluation.metrics import ask, split_sentences, support_ratio

PROMPT = (
    "Context:\n{context}\n\nSentence: {sentence}\n\n"
    "Can this sentence be attributed to the provided context? Answer with exactly one word: yes or no."
)
FALLBACK_SUPPORT = 0.6


async def evaluate_context_recall(query: str, chunks: list[str], answer: str, client=None) -> float:
    sentences = split_sentences(answer or "")
    if not sentences:
        return 0.0
    context = "\n\n".join(chunks)
    if not context.strip():
        return 0.0

    async def attributable(sentence: str) -> bool:
        verdict = await ask(PROMPT.format(context=context, sentence=sentence), client)
        if verdict is None:
            return support_ratio(sentence, context) >= FALLBACK_SUPPORT
        return verdict.strip().lower().startswith("yes")

    flags = await asyncio.gather(*(attributable(s) for s in sentences))
    return sum(flags) / len(sentences)