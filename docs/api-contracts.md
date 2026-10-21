# NeuroFlow API Contracts

## 1. Conventions

**Base URL:** `/api/v1`

**Format:** all request and response bodies are JSON (`Content-Type: application/json`), except file uploads (`multipart/form-data`) and the SSE stream (`text/event-stream`).

**IDs:** all IDs are UUIDs, returned as strings.

**Timestamps:** ISO 8601 in UTC, for example `2026-10-21T10:30:00Z`.

### 1.1 Authentication

Protected endpoints require an API key in the request header:

```
Authorization: Bearer <api_key>
```

| Level | Meaning |
|---|---|
| Public | No key needed |
| API key | Any valid key |
| Admin | A key with admin permission |

### 1.2 Rate Limits

Limits are applied per API key and counted per minute. Every response includes these headers:

| Header | Meaning |
|---|---|
| `X-RateLimit-Limit` | Requests allowed per minute |
| `X-RateLimit-Remaining` | Requests left in the current window |
| `Retry-After` | Seconds to wait (only sent with a 429 response) |

### 1.3 Standard Error Format

Every error response has the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "File type not supported",
    "details": {}
  }
}
```

### 1.4 Common Error Codes

These can be returned by any protected endpoint, so they are not repeated in each endpoint's table.

| HTTP status | `code` | Meaning |
|---|---|---|
| 400 | `bad_request` | The request is malformed. |
| 401 | `unauthorized` | The API key is missing or invalid. |
| 403 | `forbidden` | The key is valid but lacks permission. |
| 404 | `not_found` | The resource does not exist. |
| 422 | `validation_error` | The body is well-formed but a field is invalid. |
| 429 | `rate_limited` | Rate limit exceeded. |
| 500 | `internal_error` | Unexpected server error. |
| 503 | `service_unavailable` | A dependency (database, queue, LLM) is down. |

## 2. Endpoints

### 2.1 POST /ingest

Submit a file or a web URL for ingestion. The request returns right away, and the document is processed in the background (see the Ingestion Subsystem in `architecture.md`).

| | |
|---|---|
| **Method and path** | `POST /api/v1/ingest` |
| **Authentication** | API key |
| **Rate limit** | 20 requests per minute |

**Request, file upload** (`multipart/form-data`):

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes | PDF, DOCX, PNG, JPG, or CSV. Maximum 50 MB. |
| `pipeline_id` | string (UUID) | No | Pipeline configuration to use. If omitted, the default pipeline is used. |
| `metadata` | JSON string | No | Extra key-value tags stored with every chunk. |

**Request, web URL** (`application/json`):

```json
{
  "url": "https://example.com/article",
  "pipeline_id": "3f9c2a52-7a1e-4d9b-9c55-1d2f0f6b8a10",
  "metadata": {"project": "q3-research"}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | A public `http` or `https` URL. |
| `pipeline_id` | string (UUID) | No | Same as above. |
| `metadata` | object | No | Same as above. |

Exactly one of `file` or `url` must be sent.

**Success response: 202 Accepted**

```json
{
  "document_id": "b7e1c0de-5a3f-4b1e-8d52-0c9a7f3e1d44",
  "source_type": "pdf",
  "source_name": "report.pdf",
  "status": "queued",
  "created_at": "2026-10-21T10:30:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `document_id` | string (UUID) | ID used to track this document. |
| `source_type` | string | `pdf`, `docx`, `image`, `csv`, or `url`. |
| `source_name` | string | File name or URL. |
| `status` | string | Always `queued` on creation. Later values: `processing`, `ready`, `failed`. |
| `created_at` | string | Timestamp. |

**Errors** (in addition to the common errors in section 1.4):

| HTTP status | `code` | Meaning |
|---|---|---|
| 400 | `missing_input` | Neither `file` nor `url` was sent, or both were. |
| 413 | `file_too_large` | The file is over 50 MB. |
| 415 | `unsupported_file_type` | The file type is not supported. |
| 422 | `invalid_url` | The URL is malformed or not reachable. |
| 404 | `pipeline_not_found` | The given `pipeline_id` does not exist. |

### 2.2 POST /query

Start a RAG query. The request runs retrieval and starts generation, then returns a `query_id` right away. The answer itself is delivered through the stream endpoint (section 2.3).

| | |
|---|---|
| **Method and path** | `POST /api/v1/query` |
| **Authentication** | API key |
| **Rate limit** | 60 requests per minute |

**Request body:**

```json
{
  "query": "What is the refund window?",
  "pipeline_id": "3f9c2a52-7a1e-4d9b-9c55-1d2f0f6b8a10",
  "filters": {
    "source_types": ["pdf", "docx"],
    "document_ids": ["b7e1c0de-5a3f-4b1e-8d52-0c9a7f3e1d44"],
    "created_after": "2026-01-01T00:00:00Z"
  },
  "top_k": 8,
  "model_preference": "auto",
  "conversation_id": "c1d2e3f4-0000-4000-8000-000000000001"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | The user's question. 1 to 4000 characters. |
| `pipeline_id` | string (UUID) | No | Pipeline configuration to use. Default pipeline if omitted. |
| `filters` | object | No | Metadata filters applied during retrieval. |
| `filters.source_types` | array of string | No | Restrict to `pdf`, `docx`, `image`, `csv`, `url`. |
| `filters.document_ids` | array of string | No | Restrict to specific documents. |
| `filters.created_after` | string | No | Only chunks created after this timestamp. |
| `top_k` | integer | No | Number of chunks in the final context. 1 to 20, default 8. |
| `model_preference` | string | No | `auto` (router decides, the default), `fast`, `balanced`, or `best`. |
| `conversation_id` | string (UUID) | No | Links the query to earlier turns so history is included in the prompt. |

**Success response: 202 Accepted**

```json
{
  "query_id": "9a8b7c6d-1111-4222-8333-444455556666",
  "stream_url": "/api/v1/query/9a8b7c6d-1111-4222-8333-444455556666/stream",
  "status": "generating",
  "retrieved_chunks": 8,
  "model_selected": "balanced-tier-model",
  "created_at": "2026-10-21T10:31:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `query_id` | string (UUID) | ID of this query. Also used by evaluation and feedback. |
| `stream_url` | string | Where to connect to receive the answer. |
| `status` | string | `generating` on success. |
| `retrieved_chunks` | integer | How many chunks ended up in the context. 0 means nothing relevant was found. |
| `model_selected` | string | The model the router chose. |
| `created_at` | string | Timestamp. |

**Errors** (in addition to the common errors in section 1.4):

| HTTP status | `code` | Meaning |
|---|---|---|
| 400 | `empty_query` | The query is empty or only whitespace. |
| 422 | `query_too_long` | The query is over 4000 characters. |
| 422 | `invalid_filter` | A filter field is invalid, for example an unknown source type. |
| 404 | `pipeline_not_found` | The given `pipeline_id` does not exist. |
| 404 | `conversation_not_found` | The given `conversation_id` does not exist. |
| 503 | `no_model_available` | Every model the router could use is currently unavailable. |

### 2.3 GET /query/{query_id}/stream

Stream the generated answer token by token using Server-Sent Events (SSE). The client connects to the `stream_url` returned by `POST /query`.

| | |
|---|---|
| **Method and path** | `GET /api/v1/query/{query_id}/stream` |
| **Authentication** | API key (the same key that created the query) |
| **Rate limit** | 60 connections per minute |

**Path parameter:**

| Parameter | Type | Description |
|---|---|---|
| `query_id` | string (UUID) | The ID returned by `POST /query`. |

**Request headers:**

| Header | Value |
|---|---|
| `Accept` | `text/event-stream` |
| `Last-Event-ID` | Optional. The ID of the last event received, used to resume after a dropped connection. |

**Success response: 200 OK** (`Content-Type: text/event-stream`)

The server sends a series of events. Each event has an `id`, an event name, and a JSON `data` payload:

```
id: 1
event: token
data: {"text": "The refund window "}

id: 2
event: token
data: {"text": "is 30 days."}

id: 3
event: citations
data: {"citations": [{"chunk_id": "e5f6...", "source_name": "policy.pdf", "page_or_row": 4}]}

id: 4
event: done
data: {"query_id": "9a8b7c6d-...", "model_used": "balanced-tier-model", "input_tokens": 1850, "output_tokens": 42, "latency_ms": 2310}
```

| Event | When it is sent | Payload |
|---|---|---|
| `token` | Once per chunk of generated text. | `text`: the new piece of the answer. |
| `citations` | Once, after the last token. | `citations`: list of sources used, each with `chunk_id`, `source_name`, and `page_or_row`. |
| `done` | Last event, the stream then closes. | `query_id`, `model_used`, `input_tokens`, `output_tokens`, `latency_ms`. |
| `error` | If generation fails mid-stream. The stream then closes. | `code` and `message`, using the same codes as the error format in section 1.3. |

**Errors before the stream starts** (normal JSON error responses, in addition to the common errors in section 1.4):

| HTTP status | `code` | Meaning |
|---|---|---|
| 404 | `query_not_found` | No query exists with this ID, or it belongs to another API key. |
| 409 | `stream_already_consumed` | The answer was already fully streamed and the stream has expired. The finished answer is available in the evaluation log. |
| 504 | `generation_timeout` | The model did not produce output in time. |

**Notes:**

- If the client disconnects, generation still finishes in the background so the full response is logged and evaluated (see the Generation Subsystem in `architecture.md`).
- If the connection drops, the client can reconnect with `Last-Event-ID` to continue from where it stopped.

### 2.4 GET /evaluations

Return a paginated list of evaluation results, newest first. Each item is the set of scores for one generation (see the Evaluation Subsystem in `architecture.md`).

| | |
|---|---|
| **Method and path** | `GET /api/v1/evaluations` |
| **Authentication** | API key |
| **Rate limit** | 120 requests per minute |

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `page` | integer | No | Page number, starting at 1. Default 1. |
| `page_size` | integer | No | Items per page, 1 to 100. Default 20. |
| `model` | string | No | Only evaluations of answers from this model. |
| `pipeline_id` | string (UUID) | No | Only evaluations from this pipeline. |
| `min_faithfulness` | number | No | Only results with faithfulness at or above this value (0.0 to 1.0). |
| `min_rating` | integer | No | Only results with a user rating at or above this value (1 to 5). |
| `from` | string | No | Only evaluations after this timestamp. |
| `to` | string | No | Only evaluations before this timestamp. |
| `status` | string | No | `completed` or `failed`. Default `completed`. |

**Example request:**

```
GET /api/v1/evaluations?page=1&page_size=20&min_faithfulness=0.8&min_rating=4
```

**Success response: 200 OK**

```json
{
  "items": [
    {
      "evaluation_id": "d4c3b2a1-0000-4000-8000-00000000abcd",
      "query_id": "9a8b7c6d-1111-4222-8333-444455556666",
      "model_used": "balanced-tier-model",
      "pipeline_id": "3f9c2a52-7a1e-4d9b-9c55-1d2f0f6b8a10",
      "scores": {
        "faithfulness": 0.92,
        "answer_relevance": 0.88,
        "context_precision": 0.75,
        "context_recall": 0.9
      },
      "user_rating": 5,
      "judge_model": "judge-model-v1",
      "status": "completed",
      "evaluated_at": "2026-10-21T10:32:10Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total_items": 134,
  "total_pages": 7
}
```

| Field | Type | Description |
|---|---|---|
| `items` | array | The evaluations on this page. |
| `items[].evaluation_id` | string (UUID) | ID of the evaluation. |
| `items[].query_id` | string (UUID) | The query that was evaluated. |
| `items[].model_used` | string | The model that produced the answer. |
| `items[].pipeline_id` | string (UUID) | The pipeline the query ran through. |
| `items[].scores` | object | The four metrics, each 0.0 to 1.0. A value is `null` if it was skipped, for example precision and recall when the context was empty. |
| `items[].user_rating` | integer or null | The user's 1 to 5 rating, or `null` if not rated. |
| `items[].judge_model` | string | The model that produced the scores. |
| `items[].status` | string | `completed` or `failed`. |
| `items[].evaluated_at` | string | Timestamp. |
| `page`, `page_size` | integer | Echo of the pagination used. |
| `total_items` | integer | Number of evaluations matching the filters. |
| `total_pages` | integer | Number of pages available. |

**Errors** (in addition to the common errors in section 1.4):

| HTTP status | `code` | Meaning |
|---|---|---|
| 422 | `invalid_pagination` | `page` or `page_size` is out of range. |
| 422 | `invalid_filter` | A filter value is invalid, for example `min_faithfulness` above 1.0. |
| 422 | `invalid_date_range` | `from` is later than `to`. |

### 2.5 GET /evaluations/aggregate

Return rolling quality metrics computed over a time window (see Rolling Aggregates in the Evaluation Subsystem in `architecture.md`). The values come from precomputed aggregates, so the response is fast.

| | |
|---|---|
| **Method and path** | `GET /api/v1/evaluations/aggregate` |
| **Authentication** | API key |
| **Rate limit** | 60 requests per minute |

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `window` | string | No | `1h`, `24h`, or `7d`. Default `24h`. |
| `group_by` | string | No | `none`, `model`, `pipeline`, or `source_type`. Default `none`. |
| `model` | string | No | Only include answers from this model. |
| `pipeline_id` | string (UUID) | No | Only include evaluations from this pipeline. |

**Example request:**

```
GET /api/v1/evaluations/aggregate?window=7d&group_by=model
```

**Success response: 200 OK**

```json
{
  "window": "7d",
  "group_by": "model",
  "computed_at": "2026-10-21T10:40:00Z",
  "groups": [
    {
      "key": "balanced-tier-model",
      "count": 412,
      "metrics": {
        "faithfulness": {"mean": 0.87, "p5": 0.61},
        "answer_relevance": {"mean": 0.9, "p5": 0.7},
        "context_precision": {"mean": 0.78, "p5": 0.4},
        "context_recall": {"mean": 0.84, "p5": 0.5}
      },
      "mean_user_rating": 4.2
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `window` | string | The time window used. |
| `group_by` | string | The grouping used. |
| `computed_at` | string | When these aggregates were last refreshed. |
| `groups` | array | One entry per group. With `group_by=none` there is a single group with `key` set to `all`. |
| `groups[].key` | string | The group name, such as a model name. |
| `groups[].count` | integer | Number of evaluations the numbers are based on. |
| `groups[].metrics` | object | For each of the four metrics, the `mean` and the 5th percentile (`p5`). The p5 shows the worst cases that a mean hides. |
| `groups[].mean_user_rating` | number or null | Average user rating, or `null` if no ratings exist in the window. |

If no evaluations exist in the window, `groups` is an empty array.

**Errors** (in addition to the common errors in section 1.4):

| HTTP status | `code` | Meaning |
|---|---|---|
| 422 | `invalid_window` | `window` is not one of `1h`, `24h`, `7d`. |
| 422 | `invalid_group_by` | `group_by` is not one of the allowed values. |

### 2.6 POST /pipelines

Create a named pipeline configuration. A pipeline bundles the settings for ingestion, retrieval, and generation, so they can be reused by passing its `pipeline_id` to `POST /ingest` and `POST /query`.

| | |
|---|---|
| **Method and path** | `POST /api/v1/pipelines` |
| **Authentication** | API key |
| **Rate limit** | 10 requests per minute |

**Request body:**

```json
{
  "name": "legal-docs-pipeline",
  "description": "Settings tuned for long legal PDFs",
  "ingestion": {
    "chunking_strategy": "sentence",
    "chunk_size_tokens": 512,
    "chunk_overlap_tokens": 64,
    "embedding_model": "embedding-model-v1"
  },
  "retrieval": {
    "candidates": 50,
    "top_k": 8,
    "rrf_k": 60,
    "reranker_enabled": true,
    "min_rerank_score": 0.2
  },
  "generation": {
    "model_preference": "auto",
    "system_prompt": "Answer using only the provided context.",
    "max_output_tokens": 1000,
    "temperature": 0.2
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Unique name, 1 to 100 characters. |
| `description` | string | No | Free-text note. |
| `ingestion.chunking_strategy` | string | No | `fixed`, `sentence`, or `semantic`. Default `sentence`. |
| `ingestion.chunk_size_tokens` | integer | No | Target chunk size, 64 to 2048. Default 512. |
| `ingestion.chunk_overlap_tokens` | integer | No | Overlap between chunks, 0 to 256. Default 64. |
| `ingestion.embedding_model` | string | No | Which embedding model to use. System default if omitted. |
| `retrieval.candidates` | integer | No | Candidates passed to the reranker, 10 to 200. Default 50. |
| `retrieval.top_k` | integer | No | Chunks in the final context, 1 to 20. Default 8. |
| `retrieval.rrf_k` | integer | No | The constant in Reciprocal Rank Fusion. Default 60. |
| `retrieval.reranker_enabled` | boolean | No | Default `true`. |
| `retrieval.min_rerank_score` | number | No | Chunks below this score are dropped, 0.0 to 1.0. Default 0.2. |
| `generation.model_preference` | string | No | `auto`, `fast`, `balanced`, or `best`. Default `auto`. |
| `generation.system_prompt` | string | No | Instructions placed at the start of every prompt. |
| `generation.max_output_tokens` | integer | No | Limit on answer length. Default 1000. |
| `generation.temperature` | number | No | 0.0 to 1.0. Default 0.2. |

Any section or field left out uses the system default.

**Success response: 201 Created**

```json
{
  "pipeline_id": "3f9c2a52-7a1e-4d9b-9c55-1d2f0f6b8a10",
  "name": "legal-docs-pipeline",
  "description": "Settings tuned for long legal PDFs",
  "ingestion": {"chunking_strategy": "sentence", "chunk_size_tokens": 512, "chunk_overlap_tokens": 64, "embedding_model": "embedding-model-v1"},
  "retrieval": {"candidates": 50, "top_k": 8, "rrf_k": 60, "reranker_enabled": true, "min_rerank_score": 0.2},
  "generation": {"model_preference": "auto", "system_prompt": "Answer using only the provided context.", "max_output_tokens": 1000, "temperature": 0.2},
  "created_at": "2026-10-21T11:00:00Z"
}
```

The response returns the full saved configuration with all defaults filled in, plus `pipeline_id` and `created_at`.

**Errors** (in addition to the common errors in section 1.4):

| HTTP status | `code` | Meaning |
|---|---|---|
| 409 | `pipeline_name_exists` | A pipeline with this name already exists. |
| 422 | `invalid_chunking_strategy` | The strategy is not `fixed`, `sentence`, or `semantic`. |
| 422 | `invalid_config_value` | A number is outside its allowed range, or `chunk_overlap_tokens` is not smaller than `chunk_size_tokens`. |
| 422 | `unknown_embedding_model` | The embedding model is not available. |

