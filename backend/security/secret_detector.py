import re

PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_api_key": re.compile(
        r"""['"]?(?:api|secret|token|key|password)['"]?\s*[:=]\s*['"][A-Za-z0-9/+]{20,}['"]""", re.I
    ),
    "private_key": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----)?", re.S
    ),
    "jwt": re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}


def redact_secrets(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    for name, rx in PATTERNS.items():
        text, n = rx.subn("[REDACTED]", text)
        if n:
            found.append(name)
    return text, found