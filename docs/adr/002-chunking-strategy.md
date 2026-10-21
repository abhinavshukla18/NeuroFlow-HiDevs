# ADR 002: Chunking Strategy

**Status:** Accepted
**Date:** 2026-10-21

## Context

Before documents can be embedded and searched, the Ingestion Subsystem must split them into chunks. Chunking quality affects every later stage:

- Chunks that are **too large** blur several topics into one vector, which hurts retrieval precision and wastes the LLM's context window.
- Chunks that are **too small** lose the surrounding meaning, which hurts context recall and faithfulness.
- Chunks that **cut through sentences or tables** produce fragments that embed poorly and read badly when shown as citations.

NeuroFlow ingests mixed content: PDFs, DOCX files, scanned images (through OCR), CSV rows, and web pages. A single rigid method will not suit all of them.

Options considered:

| Strategy | How it works | Strengths | Weaknesses |
|---|---|---|---|
| **Fixed-size** | Split every N tokens, with some overlap. | Very fast and predictable. Chunk sizes are uniform, which makes batching and cost easy to estimate. Works on any text. | Cuts through sentences and ideas. Overlap is needed to hide the cuts, which adds duplicate storage. |
| **Sentence-boundary** | Split at sentence ends, then group sentences up to a target size (with a small overlap). | Never cuts a sentence. Keeps ideas together. Still fast and needs no model. | Chunk sizes vary a little. Depends on a sentence splitter that can fail on messy text such as OCR output or tables. |
| **Semantic** | Embed sentences, then start a new chunk where the meaning shifts. | Chunks follow topic changes, so each chunk is about one thing. | Slower and costs extra embedding calls at ingestion. Behaviour is harder to predict and tune. Gains over sentence chunking are not guaranteed. |

## Decision

Use **sentence-boundary chunking as the default**, with a target of **512 tokens** and **64 tokens of overlap**. These are the defaults in the pipeline configuration, and they can be changed per pipeline.

Apply per content type:

| Content | Strategy | Reason |
|---|---|---|
| PDF, DOCX, web pages | Sentence-boundary, respecting headings and paragraph breaks where they exist | Prose with clear structure. |
| CSV | One chunk per row, or per small group of rows, with the column headers repeated in each chunk | A row is already a natural unit, and headers give each row its meaning. |
| Images (OCR text) | Fixed-size | OCR text often has broken or missing punctuation, so sentence detection is unreliable. |

**Switching conditions.** The strategy is a per-pipeline setting, so switching is a configuration change, not a code change. NeuroFlow will switch only when evaluation data supports it:

| Condition | Switch to | Why |
|---|---|---|
| Context recall is consistently low for a pipeline, and failed queries show relevant text split across chunk boundaries | Semantic | Topic-aware boundaries may keep related text together. |
| Documents are long and cover many topics per page (reports, transcripts) and context precision is low | Semantic | Chunks may be mixing topics. |
| Sentence splitting fails often (OCR output, logs, code, text with no punctuation) | Fixed-size | Fixed-size does not depend on punctuation. |
| Ingestion cost or latency becomes a bottleneck for a very large corpus | Fixed-size | It is the cheapest and fastest method. |

**How a switch is decided:** ingest the same sample documents with each strategy into separate pipelines, run the same set of test questions, and compare the four evaluation metrics. A new strategy is adopted only if it improves context recall or context precision without lowering faithfulness, and the cost increase is acceptable.

## Consequences

**Positive:**

- Chunks stay readable and make clean citations.
- No extra model calls at ingestion, so ingestion is fast and cheap.
- The behaviour is predictable and easy to debug.
- Because the strategy is stored in the pipeline configuration, different document collections can use different strategies, and the choice can be tested without changing the code.

**Negative:**

- Sentence-boundary chunking can still split a table, a list, or a code block across chunks. Special handling for these is left for later, and the CSV rule above is the only structured-data rule for now.
- Overlap means some text is stored and embedded twice, which increases storage and embedding cost slightly. With a 512-token chunk and 64-token overlap, this is about 12%.
- The 512 and 64 values are starting points. They are not proven optimal for NeuroFlow's data until measured.

**Follow-up:**

- Changing the chunking strategy or size means existing documents must be re-chunked and re-embedded to benefit. The raw files are kept in storage for this reason (see the Ingestion Subsystem), and the pipeline used for each document is recorded in `documents.pipeline_id`.
- Chunk size and overlap will be tuned by comparing evaluation scores across a few values, such as 256, 512, and 1024 tokens.