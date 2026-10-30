# NeuroFlow operations runbook

Shorthand used below (PowerShell or bash): `dc` = `docker compose -f infra/docker-compose.yml --env-file .env`.
Tools: Jaeger http://localhost:16686, Grafana http://localhost:3001, Prometheus http://localhost:9090.
Most admin calls need an admin token (`POST /auth/token` with the admin client).

---

## Incident 1: High query latency (P95 > 10 s)

**Check**
1. Jaeger: open a slow `generation.pipeline` trace. The longest child span tells you the layer:
   `retrieval.dense|sparse|rerank` (search), `generation.llm_call` (provider), `llm.embed` (embedding).
2. Redis memory and cache hit rate:
   `dc exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" INFO memory'` and `... INFO stats`
   (compare `keyspace_hits` vs `keyspace_misses`; high `evicted_keys` means the 512 MB cap is too small).
3. Postgres slow queries (needs `pg_stat_statements`: start postgres with
   `-c shared_preload_libraries=pg_stat_statements`, then `CREATE EXTENSION pg_stat_statements;`):
   `SELECT left(query,80), calls, round(mean_exec_time) AS ms FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;`
4. Grafana "System Overview": retrieval vs generation latency panels.

**Remediation**
- Slow LLM span: check the provider status page and circuit breaker state (Incident 3).
- Slow search: confirm indexes exist (`\d chunks` shows the HNSW and GIN indexes); lower
  `retrieval.dense_k` / `sparse_k` on the pipeline; raise `retrieval.ef_search` only if recall drops.
- Cache problems: flush only embedding cache keys:
  `dc exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" --scan --pattern "embcache:*" | xargs redis-cli -a "$REDIS_PASSWORD" del'`
  (a full `FLUSHALL` also clears rate limits, circuit state and queues; avoid it).
- Scale out: `dc up -d --scale api=2` (production compose: change `replicas`).

---

## Incident 2: Evaluation scores degrading

**Check**
1. Grafana "Quality Monitor": which pipeline, which metric (faithfulness, relevance, precision, recall).
2. Recently ingested documents: `GET /documents` (newest first). Poor or noisy input (scans, boilerplate)
   lowers context precision and faithfulness.
3. Low-scoring runs: `GET /evaluations` and filter by pipeline; open the worst cards in the dashboard.
4. MLflow (http://localhost:5000, experiment `neuroflow-finetuning`): was a fine-tuned model registered
   shortly before the drop? Compare with `GET /finetune/jobs`.

**Remediation**
- Remove or re-ingest the bad document, then re-run a few queries.
- Revert the last fine-tuned model: remove its entry from the Redis key `router:models`
  (`redis-cli GET router:models`, edit, `SET`), so routing falls back to the base model.
- Inspect training data: `GET /finetune/training-data/preview`; raise the quality threshold in the
  pipeline's `evaluation.training_threshold`.
- Revert the last pipeline config change (`PATCH /pipelines/{id}` creates a new version; set the old values back).

---

## Incident 3: LLM provider circuit breaker open

**Check**
1. `GET /health`: `checks.circuit_breakers.<provider>.state` is `open`, with `opened_at`.
2. Provider status page (status.openai.com / status.anthropic.com).
3. API logs: `dc logs api --tail 100` for the repeated provider error.

**Remediation**
- Provider outage: wait. After `recovery_timeout` (60 s) the breaker goes half-open and closes on success.
- Provider is healthy again but the breaker is still open (or after fixing a bad API key):
  `POST /admin/circuit-breaker/reset` with `{"name": "openai"}` and an admin token.
  Manual fallback: `redis-cli DEL circuit:openai:state circuit:openai:failure_count circuit:openai:opened_at`.
- Verify: `GET /health` shows `closed` and `status: ok`.

---

## Incident 4: Ingestion queue depth > 100

**Check**
1. `GET /health`: `checks.queue_depth`. `POST /ingest` already returns 503 above 100.
2. Worker logs: `dc logs worker --tail 200` (look for `Ingestion failed` or repeated tracebacks).
3. Stuck jobs: `GET /documents` with documents stuck in `processing` for a long time.

**Remediation**
- Restart workers: `dc restart worker` (arq re-runs unfinished jobs, up to 3 tries).
- Add capacity: `dc up -d --scale worker=2`.
- Mark documents stuck in `processing` as failed so they can be re-uploaded:
  `UPDATE documents SET status='failed' WHERE status='processing' AND created_at < now() - interval '1 hour';`
- If an external provider is down, wait for it (Incident 3); the queue drains afterwards.

---

## Incident 5: Database disk usage > 80%

**Check**
1. Fastest-growing tables:
   `SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;`
   (`chunks` with its vector index is normally the largest.)
2. Is retention running? Look for the daily `data_retention` line in `dc logs api`.
3. Document volume: `SELECT status, count(*) FROM documents GROUP BY status;`

**Remediation**
- Run the retention job now: `dc exec -T api python -m jobs.retention`.
- Archive unneeded documents (status `archived`), then rerun retention to delete their chunks.
- Reclaim space: `VACUUM (ANALYZE) chunks;`. A full `VACUUM FULL` locks the table, so do it off-hours.
- Increase the volume size on the host/cloud provider.

---

## Data retention (daily job)

Deletes `pipeline_runs` older than 90 days that are complete and have no evaluation, evaluations older
than 180 days, and chunks of documents with status `archived`. Deleted counts are logged as
`{"event": "data_retention", ...}`. Manual run: `dc exec -T api python -m jobs.retention`.