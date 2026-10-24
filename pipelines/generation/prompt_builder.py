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


def build_system_prompt(query_type: str) -> str:
    addition = TYPE_ADDITIONS.get(query_type, TYPE_ADDITIONS["factual"])
    return f"{BASE_SYSTEM_PROMPT}\n\n{addition}"


def build_messages(query: str, context: str, query_type: str = "factual") -> list[ChatMessage]:
    user = f"<context>\n{context}\n</context>\n\n{query}"
    return [
        ChatMessage(role="system", content=build_system_prompt(query_type)),
        ChatMessage(role="user", content=user),
    ]