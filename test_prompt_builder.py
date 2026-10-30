from pipelines.generation.prompt_builder import build_messages

for qt, expected in [
    ("factual", "direct, concise"),
    ("analytical", "contradictions"),
    ("comparative", "structured comparison"),
    ("procedural", "numbered steps"),
    ("unknown", "direct, concise"),
]:
    system, user = build_messages("What is X?", "[Source 1 — a.pdf]\nX is Y.", qt)
    assert system.role == "system" and "ONLY the provided context" in system.content
    assert expected in system.content, qt
    assert user.content.startswith("<context>\n[Source 1") and user.content.endswith("</context>\n\nWhat is X?")
print("PASS")