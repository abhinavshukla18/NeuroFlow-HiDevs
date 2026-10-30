# Quality improvement log

Baseline and final metrics: `quality_baseline.json`, `quality_final.json`.
Measured with `evaluation/measure.py` (50 retrieval questions, 30 generation questions).

## 1. Redis embedding cache
**What:** `NeuroFlowClient.embed` now caches each text's embedding in Redis for 7 days, keyed by model and
a hash of the text, and only calls the provider for cache misses.
**Why:** repeated queries and re-ingested text were paying for the same embedding call every time, and the
embedding call sits on the critical path of every query.
**Before/after:** P95 query latency TODO s before, TODO s after (second run of measure.py, warm cache).
**Decision:** TODO (keep or revert).

## 2. Tunable HNSW ef_search and RRF k
**What:** two new pipeline config fields, `retrieval.ef_search` (default 40) and `retrieval.rrf_k`
(default 60). `ef_search` is applied with `SET LOCAL hnsw.ef_search` per dense query; `rrf_k` is passed to
reciprocal rank fusion.
**Why:** a higher `ef_search` trades latency for recall in the approximate vector search, and a lower
`rrf_k` makes the top ranks count for more in fusion, which can raise MRR.
**Before/after:** Hit@10 TODO to TODO, MRR@10 TODO to TODO with ef_search TODO and rrf_k TODO.
**Decision:** TODO.

## 3. System prompt A/B test (default vs precise vs concise)
**What:** three pipelines differing only in `generation.system_prompt_variant`, each run on the same 10
questions and evaluated; results are logged in MLflow under the experiment `neuroflow-prompt-ab`.
**Why:** prompt wording changes how closely the model sticks to the sources (faithfulness) and how
directly it answers (answer relevance), and the variants already existed in the config.
**Before/after:** overall score default TODO, precise TODO, concise TODO; winner TODO.
**Decision:** TODO (activate the winner by setting it on the default pipeline).