# NeuroFlow-HiDevs

NeuroFlow is a Retrieval-Augmented Generation (RAG) platform. Users upload documents, ask questions, and receive streamed answers grounded in their own data. Every answer is scored automatically for quality, and the best answers are later used to fine-tune the models.

**Current status:** Task 1, system design. This repository contains the architecture, API contracts, data models, and technology decisions. No production code has been written yet.

## System at a Glance

NeuroFlow is made of five subsystems:

| Subsystem | What it does |
|---|---|
| Ingestion | Accepts PDF, DOCX, images, CSV, and web URLs. Extracts content, chunks it, embeds it, and stores it in the vector store. |
| Retrieval | Runs vector, keyword, and metadata search in parallel, fuses results with Reciprocal Rank Fusion, and reranks with a cross-encoder. |
| Generation | Builds the prompt, routes to the right LLM, streams the answer over SSE, and logs the full input and output. |
| Evaluation | Scores every generation asynchronously on faithfulness, answer relevance, context precision, and context recall. |
| Fine-Tuning | Selects high-quality examples from the evaluation log, builds training data, runs fine-tuning jobs tracked in MLflow, and routes queries to the fine-tuned model only when it beats the base model. |

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | The five subsystems, each with a data flow diagram |
| [docs/api-contracts.md](docs/api-contracts.md) | The full REST API: 13 endpoints with schemas, errors, authentication, and rate limits |
| [docs/data-models.md](docs/data-models.md) | The Postgres tables and how they relate |
| [docs/adr/001-vector-store.md](docs/adr/001-vector-store.md) | Why pgvector for the vector store |
| [docs/adr/002-chunking-strategy.md](docs/adr/002-chunking-strategy.md) | Fixed-size vs sentence-boundary vs semantic chunking, and when to switch |
| [docs/adr/003-evaluation-framework.md](docs/adr/003-evaluation-framework.md) | Why LLM-as-judge evaluation, its failure modes, and how they are detected |

## Key Technology Decisions

- **Postgres with pgvector** holds documents, vectors, queries, evaluations, and fine-tuning jobs in one database.
- **Hybrid retrieval:** vector search and Postgres full-text search, combined with Reciprocal Rank Fusion, then reranked.
- **Sentence-boundary chunking** by default (512 tokens, 64 overlap), configurable per pipeline.
- **Server-Sent Events (SSE)** for token-by-token streaming of answers.
- **Redis job queue** so ingestion and evaluation run in the background.
- **MLflow** for tracking fine-tuning experiments.

## Repository Structure

```
NeuroFlow-HiDevs/
├── backend/        # API and subsystem services (to be implemented)
├── frontend/       # User interface (to be implemented)
├── pipelines/      # Pipeline configurations and workflows
├── evaluation/     # Evaluation and judge code
├── infra/          # Deployment and infrastructure
├── docs/           # Architecture, API contracts, data models, ADRs
├── .gitignore
└── README.md
```

## Branches

| Branch | Purpose |
|---|---|
| `main` | Stable base with the repository structure |
| `task-31` | Task 1 deliverables: architecture, API contracts, data models, and ADRs |

