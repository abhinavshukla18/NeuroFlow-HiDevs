import numpy as np

from evaluation.metrics import ask, parse_json_list, split_sentences, strip_citations
from pipelines.retrieval.retriever import default_embed

QUESTIONS_PROMPT = (
    "Generate 3 to 5 different questions that the following answer could be a response to. "
    "Return only a JSON array of strings.\n\nAnswer: {answer}"
)
LOW, HIGH = 0.45, 0.85  # fallback: cosine range of unrelated vs matching text for the local embedder


def _cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / denom) if denom else 0.0


async def evaluate_answer_relevance(query: str, answer: str, client=None, embed=default_embed) -> float:
    answer = strip_citations(answer or "")
    if not answer:
        return 0.0

    questions: list[str] = []
    raw = await ask(QUESTIONS_PROMPT.format(answer=answer), client)
    if raw:
        questions = parse_json_list(raw)[:5]

    if questions:
        vectors = await embed([query] + questions)
        sims = [_cosine(vectors[0], v) for v in vectors[1:]]
        return max(0.0, min(1.0, sum(sims) / len(sims)))

    # Fallback: compare the query with the best-matching sentence of the answer
    sentences = split_sentences(answer) or [answer]
    vectors = await embed([query] + sentences)
    best = max(_cosine(vectors[0], v) for v in vectors[1:])
    return max(0.0, min(1.0, (best - LOW) / (HIGH - LOW)))