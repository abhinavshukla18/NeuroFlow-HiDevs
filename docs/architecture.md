# NeuroFlow System Architecture

## 1. Overview

NeuroFlow is a Retrieval-Augmented Generation (RAG) platform. Users upload documents, ask questions, and receive streamed answers grounded in their own data. Every answer is automatically scored for quality, and the best answers are later used to fine-tune the models.

The system is made of five subsystems:

1. Ingestion: turns raw files into searchable vectors
2. Retrieval: finds the most relevant chunks for a query
3. Generation: builds the prompt, picks an LLM, and streams the answer
4. Evaluation: scores every answer asynchronously
5. Fine-Tuning: learns from the best answers

## 2. Ingestion Subsystem

**Purpose:** Accept raw inputs (PDF, DOCX, images, CSV, web URLs), extract content according to file type, split it into chunks, embed the chunks, and store them in the vector store so they can be searched.

### 2.1 Data Flow: File Upload to First Queryable Vector

```mermaid
flowchart TD
    A["Client: POST /ingest (file or URL)"] --> B["API validates type, size, auth"]
    B --> C["Save raw file to storage"]
    C --> D["Create document record in Postgres, status = queued"]
    D --> E["Push ingestion job to queue"]
    E --> F["Worker picks up job, status = processing"]
    F --> G{"Modality router"}
    G -->|PDF| H1["PDF text extractor"]
    G -->|DOCX| H2["DOCX parser"]
    G -->|Image| H3["OCR / vision model"]
    G -->|CSV| H4["CSV row to text converter"]
    G -->|URL| H5["Web fetcher + HTML cleaner"]
    H1 --> I["Normalized text + metadata"]
    H2 --> I
    H3 --> I
    H4 --> I
    H5 --> I
    I --> J["Chunker"]
    J --> K["Embedding model, batched"]
    K --> L["Write chunks + vectors to pgvector"]
    L --> M["Document status = ready, first queryable vector"]
```
### 2.2 Stage Descriptions

| Stage | What happens | Why |
|---|---|---|
| Validate | The API checks the auth token, file type, and file size limit. | Bad input is rejected before it costs any compute. |
| Save raw file | The original file goes to object or disk storage. | The raw file is kept so a document can be re-processed later with a new chunker or embedding model. |
| Document record | A row is created in Postgres with status `queued`. | The client gets a `document_id` back immediately and can poll for status. |
| Job queue | An ingestion job is pushed to a queue (Redis). | Extraction and embedding are slow, so they run in background workers and never block the API. |
| Modality router | The worker picks an extractor based on the file type. | Each format needs different handling. |
| Extractors | PDF and DOCX give text. Images go through OCR or a vision model. CSV rows become text. URLs are fetched and cleaned of HTML noise. | Every modality is turned into the same form: normalized text plus metadata. |
| Chunker | The text is split into chunks (strategy decided in ADR 002). | Chunks must be small enough to embed well and large enough to keep meaning. |
| Embedder | Chunks are sent to the embedding model in batches. | Batching reduces cost and API calls. |
| Vector write | Chunks, vectors, and metadata are written to pgvector (ADR 001). | This is the

### 2.4 Metadata Stored With Each Chunk

Every chunk is stored with metadata so that retrieval can filter and cite sources later.

| Field | Example | Used for |
|---|---|---|
| `chunk_id` | UUID | Unique ID of the chunk |
| `document_id` | UUID | Links the chunk back to its source document |
| `source_type` | `pdf`, `docx`, `image`, `csv`, `url` | Metadata filtering by modality |
| `source_name` | `report.pdf` or the URL | Showing citations to the user |
| `page_or_row` | `12` | Pointing to the exact location in the source |
| `chunk_index` | `5` | Keeping chunks in their original order |
| `created_at` | timestamp | Filtering by date |
| `embedding_model` | model name and version | Knowing which vectors need re-embedding if the model changes |

**Output of this subsystem:** a document with status `ready`, and its chunks stored as vectors in pgvector, searchable by the Retrieval Subsystem.

## 3. Retrieval Subsystem

**Purpose:** Given a user query, find the most relevant chunks using several search methods at once, combine the results, rerank them, and return a ranked context window for the Generation Subsystem.

### 3.1 Full Retrieval Pipeline

```mermaid
flowchart TD
    A["Client: POST /query"] --> B["Query preprocessing: clean text, extract filters"]
    B --> C["Embed the query"]
    B --> D["Keyword query"]
    B --> E["Metadata filters"]
    C --> F["Vector similarity search (pgvector)"]
    D --> G["Keyword search (Postgres full-text)"]
    E --> H["Metadata filtering"]
    F --> I["Reciprocal Rank Fusion (RRF)"]
    G --> I
    H --> I
    I --> J["Top candidates, e.g. 50"]
    J --> K["Cross-encoder reranker"]
    K --> L["Top-k chunks, e.g. 8"]
    L --> M["Context window builder: fit token budget, keep order, attach citations"]
    M --> N["Ranked context window to Generation Subsystem"]
```

### 3.2 Stage Descriptions

| Stage | What happens | Why |
|---|---|---|
| Query preprocessing | The query text is cleaned, and any filters it implies (file type, date range) are extracted. | Clean input gives better search, and filters narrow the search space. |
| Query embedding | The query is converted to a vector with the same embedding model used at ingestion. | Query and chunk vectors must come from the same model to be comparable. |
| Vector search | pgvector returns the chunks whose vectors are closest to the query vector. | Finds chunks that match in meaning, even with different wording. |
| Keyword search | Postgres full-text search returns chunks that contain the query terms. | Finds exact matches such as names, IDs, and rare terms that embeddings can miss. |
| Metadata filtering | Chunks are restricted by fields such as `source_type` or `created_at`. | Lets users scope a query, for example "only PDFs from this year". |
| Reciprocal Rank Fusion | The ranked lists are merged into one list (see 3.3). | Combines different search methods without needing to compare their raw scores. |
| Cross-encoder reranker | A model reads the query and each candidate chunk together and scores how relevant the pair is. | More accurate than vector search, but too slow to run on every chunk, so it only runs on the top candidates. |
| Context window builder | The top chunks are trimmed to fit the LLM's token budget, kept in a sensible order, and tagged with citation info. | The output must fit the model's context limit and let the answer cite its sources. |

The three searches run in parallel, so total latency is set by the slowest one, not the sum of all three.

### 3.3 Reciprocal Rank Fusion (RRF)

Vector scores and keyword scores are on different scales, so they can't be added directly. RRF avoids this by using only each chunk's **rank** in each list:

```
RRF_score(chunk) = sum over all lists of 1 / (k + rank_in_that_list)
```

`k` is a constant, usually 60, that stops the top ranks from dominating.

**Example:**

- Chunk A is rank 1 in vector search and rank 3 in keyword search: 1/61 + 1/63 ≈ 0.0323
- Chunk B is rank 2 in vector search and missing from keyword search: 1/62 ≈ 0.0161

Chunk A wins because both methods agree it is relevant. Chunks are then sorted by RRF score and the top candidates go to the reranker.

### 3.4 Inputs and Outputs

**Input:** a query string, plus optional filters (source type, date range, document IDs) and a pipeline configuration (how many candidates and top-k chunks to use).

**Output:** a ranked context window, which is a list of chunks, each containing:

| Field | Purpose |
|---|---|
| `chunk_id` and `text` | The content to put in the prompt |
| `source_name` and `page_or_row` | Citation information |
| `rerank_score` | How relevant the reranker judged the chunk |
| `rank` | Position in the final ordering |

The retrieved chunk IDs are also saved with the query record, so the Evaluation Subsystem can later measure context precision and context recall.

### 3.5 Edge Cases

- **No relevant chunks found:** if every reranker score is below a minimum threshold, the subsystem returns an empty context. The Generation Subsystem then tells the user it could not find relevant information, instead of letting the LLM guess.
- **One search method fails or times out:** the pipeline continues with the remaining methods, and the failure is logged.
- **Filters match nothing:** the subsystem returns an empty context and reports that the filters were too narrow.



## 4. Generation Subsystem

**Purpose:** Take the ranked context window from retrieval, build a prompt, route the request to the most suitable LLM, stream the answer to the client token by token, and log the full input and output for evaluation.

### 4.1 Generation Pipeline

```mermaid
flowchart TD
    A["Ranked context window from Retrieval"] --> B["Prompt assembler: system prompt + context + question + history"]
    B --> C["Model router: cost tier, capability, domain"]
    C --> D["Selected LLM"]
    D --> E["Token stream"]
    E --> F["SSE stream to client: GET /query/id/stream"]
    E --> G["Full response collected"]
    G --> H["Generation log written to Postgres"]
    H --> I["Evaluation job queued"]
```

### 4.2 Stage Descriptions

| Stage | What happens | Why |
|---|---|---|
| Prompt assembler | Builds the final prompt from a system prompt, the retrieved chunks (labelled with citation IDs), the conversation history, and the user's question. | The model must answer from the provided context and be able to cite it. |
| Model router | Chooses which LLM handles the request (see 4.3). | Balances cost, speed, and quality instead of using one model for everything. |
| LLM call | The prompt is sent to the selected model with streaming turned on. | Streaming lets the user start reading right away. |
| SSE stream | Tokens are forwarded to the client over Server-Sent Events as they arrive. | Much lower perceived latency than waiting for the full answer. |
| Response collector | The tokens are also collected into the full response in the background. | The complete answer is needed for logging and evaluation. |
| Generation log | The full input and output are written to Postgres (see 4.4). | Evaluation and fine-tuning both depend on this record. |
| Evaluation job | A job is pushed to the queue once the response is complete. | Scoring happens asynchronously so the user never waits for it. |

### 4.3 Model Routing

The router picks a model using four signals:

| Signal | Example |
|---|---|
| Cost tier | Simple questions go to a cheaper model, complex ones to a stronger model. |
| Capability | Long context needs a model with a large context window. Image content needs a vision model. |
| Domain | Code or technical questions may go to a model that is stronger at those. |
| Fine-tuned model | If a fine-tuned model has been shown to beat the base model on similar queries, it is chosen (see the Fine-Tuning Subsystem). |

If the chosen model fails or times out, the router falls back to the next model in its list. The full routing matrix will be designed in ADR 004 (the optional extra ADR).

### 4.4 What Is Logged

For every generation, one record is saved:

| Field | Purpose |
|---|---|
| `query_id` | Links the record to the query |
| `prompt` | The exact prompt sent to the model |
| `retrieved_chunk_ids` | Which chunks were in the context |
| `model_used` | Which model answered |
| `response` | The full answer |
| `input_tokens`, `output_tokens` | Cost tracking |
| `latency_ms` | Speed tracking, including time to first token |
| `created_at` | Timestamp |

### 4.5 Edge Cases

- **Empty context from retrieval:** the prompt tells the model to say it could not find relevant information, and the router uses the cheapest tier, since no reasoning over documents is needed.
- **Context too large for the model:** the context window builder drops the lowest-ranked chunks until the prompt fits the model's token limit.
- **Model fails mid-stream:** the stream sends an error event to the client, the partial response is logged with status `failed`, and the router's fallback model can be used if the client retries.
- **Client disconnects early:** the generation still finishes in the background, so the full response is logged and evaluated.

**Output of this subsystem:** a streamed answer to the client, plus a complete generation log record that feeds the Evaluation Subsystem.



## 5. Evaluation Subsystem

## 6. Fine-Tuning Subsystem