from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

DESCRIPTION = (
    "NeuroFlow is a retrieval-augmented generation platform. Typical flow: "
    "1) `POST /auth/token`, then click **Authorize** and paste the token; "
    "2) `POST /ingest` a document and poll `GET /documents/{id}` until `complete`; "
    "3) `POST /query` and read the answer (or stream it); 4) `GET /evaluations/{run_id}` for quality scores."
)

TAGS = [
    {"name": "Auth", "description": "Get a JWT access token."},
    {"name": "Ingestion", "description": "Upload documents and inspect their chunks."},
    {"name": "Query", "description": "Ask questions, stream answers, rate responses."},
    {"name": "Evaluation", "description": "Automatic quality scores and comparisons."},
    {"name": "Pipelines", "description": "Named, versioned retrieval and generation configurations."},
    {"name": "Fine-Tuning", "description": "Turn high-quality answers into fine-tuning jobs."},
    {"name": "Admin", "description": "Operational controls. Requires the admin scope."},
    {"name": "System", "description": "Health and metrics. No authentication."},
]

D = {
    ("post", "/auth/token"): ("Get an access token", "Exchange a client id and secret for a JWT valid for one hour. Scopes: query, ingest, admin. Returns 401 on wrong credentials. Fast (no database call).", "Bearer token and its lifetime in seconds.", "Auth"),
    ("post", "/ingest"): ("Ingest a document or URL", "Upload a file (multipart field `file`: pdf, docx, csv, txt, png, jpg, webp, up to 100 MB) or send JSON `{\"url\": \"https://...\"}`. Needs the ingest scope. Returns immediately; processing is asynchronous, so poll `GET /documents/{id}`. Re-uploading identical content returns the existing document with `duplicate: true`. Errors: 400 bad URL (private addresses are blocked), 415 file type or content mismatch, 429 rate limit (10/hour per IP), 503 queue full.", "The document id and its initial status.", "Ingestion"),
    ("get", "/documents"): ("List documents", "Returns the 200 most recent documents with status and chunk count.", "List of documents.", "Ingestion"),
    ("get", "/documents/{document_id}"): ("Get a document", "Use to poll ingestion: status goes queued, processing, complete (or failed, with the reason in metadata). 404 if unknown.", "Document details and status.", "Ingestion"),
    ("get", "/documents/{document_id}/chunks"): ("List a document's chunks", "Returns every chunk of a document in order. Useful for checking what was extracted.", "Chunks with token counts.", "Ingestion"),
    ("get", "/chunks/{chunk_id}"): ("Get one chunk", "Returns a chunk with its document metadata. This is what a citation points at.", "Chunk content and source document.", "Ingestion"),
    ("get", "/chunks/{chunk_id}/similar"): ("Find similar chunks", "Vector similarity search across all documents, starting from one chunk. 404 if the chunk has no embedding.", "Closest chunks with similarity scores.", "Ingestion"),
    ("post", "/query", ): ("Run a RAG query", "Retrieves relevant chunks, generates a cited answer and queues an automatic evaluation. With `stream: false` the full answer is returned (typically 2 to 6 s). With `stream: true` you get a `run_id` and read tokens from `stream_url`. Queries that look like prompt injection are rejected with 400 `query_rejected`. Limit: 60 requests/minute per IP.", "The answer with citations, or a run id to stream.", "Query"),
    ("get", "/query/{run_id}/stream"): ("Stream an answer (SSE)", "Server-sent events: `retrieval_start`, `retrieval_complete` (with sources), `token` (one per piece of text), `done` (with citations) or `error`. Each run can be streamed once (409 afterwards). Browsers can pass the token as `?token=`.", "An event stream.", "Query"),
    ("patch", "/runs/{run_id}/rating"): ("Rate an answer", "Send 1 to 5. Ratings of 4 or more keep a run eligible as fine-tuning data; low ratings exclude it.", "The stored rating.", "Query"),
    ("get", "/evaluations"): ("List recent evaluations", "Returns up to 200 evaluations with the four metric scores and the overall score.", "Evaluations, newest first.", "Evaluation"),
    ("get", "/evaluations/stream"): ("Stream new evaluations (SSE)", "Emits one event for each evaluation as soon as it is saved. Use it for live dashboards.", "An event stream.", "Evaluation"),
    ("get", "/evaluations/{run_id}"): ("Get the evaluation of a run", "Evaluation runs a few seconds after the answer finishes, so 404 right after a query means not ready yet; retry.", "Faithfulness, answer relevance, context precision, context recall and overall score.", "Evaluation"),
    ("post", "/pipelines"): ("Create a pipeline", "Creates a named pipeline (version 1). Unknown config fields are rejected with 422. Needs the admin scope. 409 if the name exists.", "The new pipeline id and version.", "Pipelines"),
    ("get", "/pipelines"): ("List pipelines", "Returns pipelines with run counts and average overall score.", "List of pipelines.", "Pipelines"),
    ("get", "/pipelines/{pipeline_id}"): ("Get a pipeline", "Returns the current config and version.", "Pipeline details.", "Pipelines"),
    ("patch", "/pipelines/{pipeline_id}"): ("Update a pipeline", "Merges the given fields into the config and creates a new version. Needs the admin scope.", "The new version number.", "Pipelines"),
    ("delete", "/pipelines/{pipeline_id}"): ("Archive a pipeline", "Soft delete: the pipeline is archived, its runs stay. Needs the admin scope.", "Confirmation.", "Pipelines"),
    ("post", "/pipelines/compare"): ("Compare two pipelines (A/B)", "Runs the same query through two pipelines in parallel and returns both answers with scores. Slow (waits for both evaluations).", "Both results side by side.", "Evaluation"),
    ("get", "/pipelines/{pipeline_id}/runs"): ("List a pipeline's runs", "Paginated run history with latency, tokens and scores.", "A page of runs.", "Evaluation"),
    ("get", "/pipelines/{pipeline_id}/analytics"): ("Pipeline analytics", "P50/P95/P99 latency, average scores, cost per query and queries per day.", "Aggregated statistics.", "Evaluation"),
    ("post", "/finetune/jobs"): ("Start a fine-tuning job", "Extracts qualifying training pairs (quality at least 0.82, faithful, cited, no personal data), writes the JSONL file, logs an MLflow run and submits the job. Needs the admin scope. 400 if no pair qualifies.", "The job id and the number of pairs used.", "Fine-Tuning"),
    ("get", "/finetune/jobs"): ("List fine-tuning jobs", "All jobs with status and pair counts.", "List of jobs.", "Fine-Tuning"),
    ("get", "/finetune/jobs/{job_id}"): ("Get a fine-tuning job", "Detailed status including metrics and the MLflow run URL.", "Job details.", "Fine-Tuning"),
    ("get", "/finetune/training-data/preview"): ("Preview training data", "Shows five sample pairs that a job would use now, without starting one.", "Qualifying count, rejection reasons and samples.", "Fine-Tuning"),
    ("post", "/admin/circuit-breaker/reset"): ("Reset a circuit breaker", "Closes a provider circuit breaker immediately. Use when the provider has recovered. Needs the admin scope.", "The breaker name and its new state.", "Admin"),
    ("get", "/health"): ("Health check", "Postgres, Redis, MLflow, circuit breakers and queue depth. `status` is ok, degraded (a circuit is open) or critical (Postgres or Redis down, HTTP 503). No authentication.", "Overall status and per-component checks.", "System"),
    ("get", "/metrics"): ("Prometheus metrics", "Text exposition format for Prometheus. No authentication.", "Prometheus metrics.", "System"),
}


def install_openapi(app: FastAPI) -> None:
    def custom():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title="NeuroFlow API", version="1.0.0", description=DESCRIPTION, routes=app.routes)
        schema["tags"] = TAGS
        for path, ops in schema["paths"].items():
            for method, op in ops.items():
                doc = D.get((method, path))
                if not doc:
                    continue
                summary, description, response_description, tag = doc
                op["summary"], op["description"], op["tags"] = summary, description, [tag]
                for code, resp in op.get("responses", {}).items():
                    if code.startswith("2"):
                        resp["description"] = response_description
                        break
        app.openapi_schema = schema
        return schema

    app.openapi = custom