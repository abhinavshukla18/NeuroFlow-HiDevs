import json
import re
from pathlib import Path
from uuid import UUID

MIN_QUALITY = 0.82
MIN_FAITHFULNESS = 0.8
MIN_TOKENS = 50
MAX_TOKENS = 2000
TRAINING_DIR = Path("training_data")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3,5}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}")
CITATION_RE = re.compile(r"\[Source \d+\]")

FETCH_SQL = """
SELECT tp.id, tp.run_id, tp.system_prompt, tp.user_message,
       tp.assistant_message, tp.quality_score, tp.created_at,
       ev.faithfulness
FROM training_pairs tp
LEFT JOIN LATERAL (
    SELECT e.faithfulness, e.user_rating
    FROM evaluations e
    WHERE e.run_id = tp.run_id
    ORDER BY e.evaluated_at DESC
    LIMIT 1
) ev ON true
WHERE tp.quality_score >= $1
  AND tp.included_in_job IS NULL
  AND (ev.user_rating IS NULL OR ev.user_rating >= 4)
ORDER BY tp.created_at DESC
LIMIT $2
"""


def count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def question_of(user_message: str) -> str:
    return user_message.split("[Question]", 1)[-1]


def has_pii(text: str) -> bool:
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text))


def validate_pair(row) -> str | None:
    answer = row["assistant_message"] or ""
    tokens = count_tokens(answer)
    if tokens < MIN_TOKENS or tokens > MAX_TOKENS:
        return "response_length"
    if not CITATION_RE.search(answer):
        return "no_citation"
    faith = row["faithfulness"]
    if faith is None or faith <= MIN_FAITHFULNESS:
        return "faithfulness"
    if has_pii(question_of(row["user_message"] or "")):
        return "pii"
    return None


def format_pair(row) -> dict:
    return {
        "messages": [
            {"role": "system", "content": row["system_prompt"]},
            {"role": "user", "content": row["user_message"]},
            {"role": "assistant", "content": row["assistant_message"]},
        ]
    }


async def extract_training_pairs(pool, limit: int = 1000):
    """Returns (valid_rows, rejected_counts)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(FETCH_SQL, MIN_QUALITY, limit)
    valid, rejected = [], {}
    for row in rows:
        reason = validate_pair(row)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
        else:
            valid.append(row)
    return valid, rejected


def write_jsonl(job_id: UUID, rows) -> str:
    TRAINING_DIR.mkdir(exist_ok=True)
    path = TRAINING_DIR / f"{job_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(format_pair(row), ensure_ascii=False) + "\n")
    return str(path)


async def mark_included(pool, job_id: UUID, rows) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE training_pairs SET included_in_job = $1 WHERE id = ANY($2::uuid[])",
            job_id,
            [r["id"] for r in rows],
        )