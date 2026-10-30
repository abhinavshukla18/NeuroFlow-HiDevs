# Retrospective

**Hardest task.** Task 12, observability, was harder than it looked. The difficulty was not Prometheus
configuration but making instrumentation agree with how the system is deployed. Ingestion and evaluation run in the
worker, while Prometheus scrapes the API, so counters incremented in the worker were invisible until the worker got
its own metrics port and the evaluation gauges were rebuilt from the database at scrape time. Tracing had the same
shape: a span only nests correctly if the parent context survives async boundaries, which meant attaching it
explicitly around retrieval and inside the streaming generator.

**A decision I would change.** Redis does too many jobs. The job queue, embedding cache, rate-limit windows,
circuit-breaker state, model-router config and evaluation pub/sub share one instance and one logical database, with
an `allkeys-lru` eviction policy. Memory pressure can evict a breaker or rate-limit key, and a careless `FLUSHALL`
(my own runbook warns against it) removes the queue and router config together. With hindsight I would separate
durable state (queue, router config) from disposable state (caches, counters), in different logical databases or
different instances. [Link the matching ADR here.]

**What tutorials don't teach.** Most failures were not model failures. They were wiring and deployment failures: an
image built before a dependency was added crashed on import, a non-root container could not write to a volume
created by root, a stale image silently ran old code, and a correct rate limiter blocked my own load test. Security
and resilience features interact, so operational switches such as `DISABLE_RATE_LIMIT` have to be designed in, not
bolted on. A test environment can also lie: with fake embeddings and a heuristic judge, retrieval metrics looked
perfect and meant nothing. Finally, hand-editing deeply nested async code is where indentation bugs breed; small
helper functions beat clever nesting.

**What the quality sprint taught me.** Measure first, and measure with enough data. My first baseline used four
questions and reported a Hit Rate of 1.0, which says nothing about quality. It did expose real weaknesses: context
precision of 0.43 against a 0.72 target, and a P95 latency of 6.7 s against 4 s, with a plausible infrastructure
cause (the reranker's model cache was not writable by the non-root user, so it could not be stored). I made each
improvement a configuration parameter (`ef_search`, `rrf_k`, the prompt variant, an embedding cache) so each can be
A/B tested and reverted, and I wrote the log to record decisions including reverts. I did not finish the sprint: the
targets are not demonstrated on a real corpus, and I would rather say so than publish an invented table.

**Next.** Stand up a real staging environment, ingest a proper corpus with real embeddings, and rerun the sprint
with enough questions that the numbers mean something.