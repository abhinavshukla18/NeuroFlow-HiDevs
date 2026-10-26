from providers.base import ChatMessage

BASE_SYSTEM_PROMPT = """You are a precise research assistant. Answer the user's question using ONLY the provided context.
If the context does not contain enough information to answer fully, say so explicitly.
For every factual claim, include a citation in the format [Source N].
Do not introduce information not present in the context."""

TYPE_ADDITIONS = {
    "factual": "Provide a direct, concise answer. If multiple sources agree, cite all of them.",
    "analytical": "Analyze and synthesize across the provided sources. Identify agreements and contradictions.",
    "comparative": "Organize your response as a structured comparison. Use a table if appropriate.",
    "procedural": "Provide numbered steps. Each step must be cited.",
}

VARIANTS = {
    "default": "",
    "precise": "Be exact: reproduce numbers, names and clause wording precisely, and avoid paraphrasing key terms.",
    "concise": "Keep the answer under 120 words.",
}


def build_system_prompt(query_type: str, variant: str = "default") -> str:
    addition = TYPE_ADDITIONS.get(query_type, TYPE_ADDITIONS["factual"])
    parts = [BASE_SYSTEM_PROMPT, addition, VARIANTS.get(variant, "")]
    return "\n\n".join(p for p in parts if p)


def build_messages(query: str, context: str, query_type: str = "factual", variant: str = "default") -> list[ChatMessage]:
    user = f"<context>\n{context}\n</context>\n\n{query}"
    return [
        ChatMessage(role="system", content=build_system_prompt(query_type, variant)),
        ChatMessage(role="user", content=user),
    ]