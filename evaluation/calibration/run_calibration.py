import asyncio
import json
from pathlib import Path

import numpy as np

from evaluation.metrics import llm_available
from evaluation.metrics.faithfulness import evaluate_faithfulness


async def main():
    rows = json.loads(Path(__file__).with_name("annotated_set.json").read_text(encoding="utf-8"))
    client = None
    if llm_available():
        from providers.client import get_client
        client = get_client()

    auto = [await evaluate_faithfulness(r["query"], r["answer"], r["context"], client) for r in rows]
    human = [r["human_score"] for r in rows]
    correlation = float(np.corrcoef(auto, human)[0, 1])

    report = {
        "metric": "faithfulness",
        "examples": len(rows),
        "judge": "llm-judge" if client else "heuristic-fallback (no LLM API key available)",
        "pearson_correlation": round(correlation, 4),
        "threshold": 0.85,
        "passed": correlation > 0.85,
        "mean_auto_score_by_kind": {
            kind: round(float(np.mean([a for a, r in zip(auto, rows) if r["kind"] == kind])), 3)
            for kind in ("faithful", "partial", "unfaithful")
        },
        "note": "Examples are synthetic, written with human faithfulness scores equal to supported claims over total claims. "
                "This is a smoke test of the judge, not a measure of real-world judge quality.",
    }
    out = Path(__file__).parent.parent / "calibration_results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


asyncio.run(main())