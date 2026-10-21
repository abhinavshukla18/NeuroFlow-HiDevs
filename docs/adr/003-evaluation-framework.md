# ADR 003: Evaluation Framework

**Status:** Accepted
**Date:** 2026-10-21

## Context

NeuroFlow needs to know whether its answers are good. Quality has to be measured on every generation, because:

- Retrieval and generation settings change often (chunking, reranker, model routing), and each change needs a measured before-and-after comparison.
- The Fine-Tuning Subsystem selects training data using evaluation scores, so poor scoring would directly train the model on poor answers.
- Problems such as hallucination must be caught quickly, not after users complain.

Options considered:

| Option | Strengths | Weaknesses |
|---|---|---|
| **Human annotation only** | Most trusted signal. Catches subtle errors and tone problems. | Slow and expensive. Cannot cover every generation. Annotators disagree with each other. Feedback arrives days later, so regressions go unnoticed. |
| **LLM-as-judge only** | Cheap and fast. Scores every generation within seconds, asynchronously. Consistent criteria. Scales with traffic. | Judges have their own biases and can be wrong. Quality depends on the judge model and prompt. |
| **Automated judge plus a small human-labelled sample** | Keeps the coverage of automation and uses humans to check it. | Needs some ongoing human effort. |

## Decision

Use **automated LLM-as-judge evaluation on every generation**, validated against a **small, regularly refreshed human-labelled sample**.

- The judge scores four metrics: faithfulness, answer relevance, context precision, and context recall (see the Evaluation Subsystem in `architecture.md`).
- Scoring runs asynchronously after the answer is streamed, so users never wait for it.
- Humans do not score every answer. They label a sample, and that sample is used to measure how far the judge can be trusted.
- User ratings (1 to 5) are collected as a separate, independent signal. Fine-tuning data selection requires both a high faithfulness score and a high user rating, so neither signal alone can admit a training example.

Automated scoring is used because human-only annotation cannot give the coverage or speed that daily changes to the system require. The human sample is kept because an unchecked judge is a risk, not a measurement.

## Failure Modes and How to Detect Them

| Failure mode | What it looks like | How it will be detected |
|---|---|---|
| **Judge disagrees with humans** | Judge scores are high on answers humans consider wrong, or the reverse. | Each month, humans label a random sample (for example 100 generations) on the same four metrics. Compare with the judge using correlation and mean absolute difference. Alert if agreement falls below a set threshold. |
| **Self-preference bias** | A judge favours answers written by the same model family. | Never use the same model as both generator and judge for the same answer where avoidable. Compare the judge's scores for different generator models on the same human-labelled set. |
| **Verbosity and position bias** | Longer answers score higher regardless of quality, or the order of items changes the score. | Test with controlled pairs: the same answer padded with filler, and the same candidates in swapped order. Track the correlation between answer length and score. |
| **Judge drift** | Scores shift over time because the judge model was updated or silently changed. | Keep a fixed "golden set" of generations with known scores. Re-run it on a schedule and after any judge change. Record `judge_model` on every evaluation row, and alert if golden-set scores move. |
| **Judge errors on hard cases** | The judge misses subtle unsupported claims, or fails on long contexts, tables, or numbers. | Review the lowest-agreement cases from the human sample. Add targeted test cases for these categories to the golden set. |
| **Metric gaming** | The generator learns to produce answers that score well but are not actually helpful, for example overly cautious or very short answers. | Watch for a rise in scores with no rise in user ratings. Track answer length and refusal rate next to the scores. Keep user rating as a separate signal. |
| **Inconsistent scoring** | The same input gets different scores on different runs. | Run the judge at low temperature. Periodically re-score a sample and measure the variance. |
| **Feedback loop into fine-tuning** | The fine-tuned model is trained on what the judge likes, and drifts toward the judge's biases. | The faithfulness AND rating rule. Compare the fine-tuned model against the base model on a held-out set that includes human-labelled examples, not only judge-scored ones. |

## Consequences

**Positive:**

- Every generation is scored, so regressions are visible quickly, within the rolling aggregates exposed by `GET /evaluations/aggregate`.
- Changes to chunking, retrieval, or routing can be compared with numbers, which is what ADR 002 relies on.
- Cost per evaluation is low compared with human labelling, and it scales with traffic.
- The four metrics separate retrieval problems (precision, recall) from generation problems (faithfulness, relevance), so a low score points at the part of the system to fix.

**Negative:**

- Every evaluation costs extra LLM calls, roughly one judge call per metric per generation. This can be reduced by sampling a fraction of traffic once volume is high.
- Scores are estimates, not ground truth. They should be read as trends and comparisons, not as exact accuracy.
- Maintaining the human-labelled sample and the golden set is ongoing work.
- The judge is itself an LLM that can be wrong, so the system is only as trustworthy as the checks above.

**Follow-up:**

- The first human-labelled sample is collected before the fine-tuning pipeline is switched on, so there is a baseline of judge-human agreement.
- Any change to the judge model or judge prompt is treated like a model release. The golden set is re-run, and the change is recorded in `judge_model`.

