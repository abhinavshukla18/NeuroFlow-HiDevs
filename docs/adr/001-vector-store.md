# ADR 001: Vector Store

**Status:** Accepted
**Date:** 2026-10-21

## Context

NeuroFlow needs to store chunk embeddings and search them by similarity. The Retrieval Subsystem runs vector search, keyword search, and metadata filtering in parallel, then fuses the results with Reciprocal Rank Fusion.

Requirements that shape this choice:

- **Hybrid retrieval.** Vector search, full-text search, and metadata filters must all run against the same chunks.
- **Transactional consistency.** A document's status, its chunks, and its vectors should be written together, so a failed ingestion never leaves half-written data that looks searchable.
- **Joins with other data.** Evaluation needs to join chunks to queries and evaluations, and fine-tuning needs to join evaluations to queries.
- **Low operational overhead.** This is a project built and run by one developer. Every extra service is something to deploy, secure, monitor, and keep in sync.
- **Moderate scale.** The expected corpus is thousands to low millions of chunks, not billions.

Options considered:

| Option | Type | Strengths | Weaknesses for this project |
|---|---|---|---|
| **pgvector** | Postgres extension | Same database as everything else. Full SQL, joins, transactions, and built-in full-text search. One system to run. | Slower than purpose-built engines at very large scale. Fewer vector-specific features. |
| **Pinecone** | Managed vector service | No infrastructure to run. Scales easily. | Separate paid service. Vectors live apart from the rest of the data, so syncing and joining are manual. Not self-hostable, and keyword search is limited. |
| **Weaviate** | Vector database | Built-in hybrid search and modules. Good feature set. | A second stateful service to run. Data must be kept in sync with Postgres. |
| **Qdrant** | Vector database | Fast, strong filtering, good performance at scale. | A second stateful service to run. Keyword search is weaker than Postgres full-text. Same sync problem. |

## Decision

Use **pgvector** inside the same Postgres database that holds every other NeuroFlow table.

- Vectors are stored in the `chunks` table as `VECTOR` columns, indexed with **HNSW** using cosine distance.
- Keyword search uses a Postgres `tsvector` column with a GIN index on the same table.
- Metadata filters are ordinary SQL conditions on the same table.
- All three searches therefore run against one table, in one database, and can be fused with RRF in application code.

## Consequences

**Positive:**

- **One system to run.** No separate vector service to deploy, secure, back up, or monitor.
- **Atomic writes.** A document and its chunks are committed in one transaction, so there is no state where a vector exists without its metadata.
- **No synchronisation problem.** Deleting a document removes its vectors in the same step (`ON DELETE CASCADE`).
- **Hybrid search is simple.** Vector, keyword, and metadata filters all hit the same table, and the evaluation and fine-tuning tables can be joined in plain SQL.
- **Low cost.** No per-vector or per-query fees from a separate vendor.

**Negative:**

- **Scale ceiling.** Performance and index build time degrade as the corpus grows into the tens of millions of vectors. Vector search also competes with transactional work for the same database resources.
- **Fewer vector features.** Purpose-built engines offer more tuning options, built-in sharding, and more index types.
- **Dimension is fixed per column.** Changing the embedding model to one with a different dimension means re-embedding all chunks into a new column or table. This is why `embedding_model` is stored on every chunk.

**Mitigations:**

- All vector access goes through the Retrieval Subsystem, so the storage layer can be replaced without changing the API in `api-contracts.md`.
- HNSW index settings (`m`, `ef_construction`, `ef_search`) will be tuned against recall and latency measurements, not left at defaults.

**When to revisit this decision:**

| Signal | Action |
|---|---|
| Vector search p95 latency stays above target after index tuning | Consider a dedicated vector database such as Qdrant, keeping Postgres as the source of truth. |
| The corpus grows past what one Postgres instance handles comfortably | Shard, or move vectors to a dedicated engine. |
| Vector queries start slowing down transactional traffic | Move search to a read replica, then to a dedicated engine if that is not enough. |