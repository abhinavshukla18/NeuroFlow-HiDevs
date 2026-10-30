import asyncio
import json
import mimetypes
import time
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from .models import Document, EvaluationResult, QueryResult


class NeuroFlowError(Exception):
    """Raised when the API returns an error or a job fails."""


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after")
    if header and header.isdigit():
        return min(float(header), 60.0)
    return min(2.0 ** attempt, 30.0)


class NeuroFlowClient:
    def __init__(self, base_url: str, api_key: str, *, max_retries: int = 5, timeout: float = 120.0):
        """api_key is either a ready bearer token or "client_id:client_secret"."""
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._token: str | None = None
        self.max_retries = max_retries
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self.last_run_id: str | None = None

    async def __aenter__(self) -> "NeuroFlowClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---- internals ----
    async def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            if ":" in self._api_key:
                client_id, secret = self._api_key.split(":", 1)
                r = await self._http.post(
                    "/auth/token", json={"client_id": client_id, "client_secret": secret}
                )
                if r.status_code != 200:
                    raise NeuroFlowError(f"Login failed ({r.status_code}): {r.text[:200]}")
                self._token = r.json()["access_token"]
            else:
                self._token = self._api_key
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        base_headers = kwargs.pop("headers", {})
        refreshed = False
        for attempt in range(self.max_retries + 1):
            headers = {**base_headers, **await self._auth_headers()}
            r = await self._http.request(method, url, headers=headers, **kwargs)
            if r.status_code == 401 and ":" in self._api_key and not refreshed:
                self._token, refreshed = None, True  # token expired: log in again once
                continue
            if r.status_code == 429 and attempt < self.max_retries:
                await asyncio.sleep(_retry_delay(r, attempt))
                continue
            return r
        return r

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 400:
            raise NeuroFlowError(f"{r.status_code}: {r.text[:300]}")

    async def _wait_for_document(self, document_id: str, timeout: float, poll: float = 2.0) -> Document:
        deadline = time.monotonic() + timeout
        while True:
            r = await self._request("GET", f"/documents/{document_id}")
            self._check(r)
            body = r.json()
            if body["status"] == "complete":
                return Document(document_id, body["filename"], body["status"], body.get("chunk_count"))
            if body["status"] == "failed":
                raise NeuroFlowError(f"Ingestion failed: {body.get('metadata')}")
            if time.monotonic() > deadline:
                raise NeuroFlowError(f"Timed out waiting for document {document_id} ({body['status']})")
            await asyncio.sleep(poll)

    # ---- ingestion ----
    async def ingest_file(
        self, file_path: str | Path, pipeline_id: str | None = None, timeout: float = 300.0
    ) -> Document:
        """Upload and ingest a file. Waits for ingestion to complete.

        pipeline_id is accepted for forward compatibility; ingestion is not pipeline-specific yet.
        """
        path = Path(file_path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        r = await self._request("POST", "/ingest", files={"file": (path.name, path.read_bytes(), mime)})
        self._check(r)
        body = r.json()
        doc = await self._wait_for_document(body["document_id"], timeout)
        doc.duplicate = bool(body.get("duplicate"))
        return doc

    async def ingest_url(self, url: str, pipeline_id: str | None = None, timeout: float = 300.0) -> Document:
        """Ingest a URL. Waits for ingestion to complete."""
        r = await self._request("POST", "/ingest", json={"url": url})
        self._check(r)
        body = r.json()
        doc = await self._wait_for_document(body["document_id"], timeout)
        doc.duplicate = bool(body.get("duplicate"))
        return doc

    # ---- query ----
    def query(self, query: str, pipeline_id: str | None = None, stream: bool = False):
        """Run a RAG query.

        stream=False: `await client.query(q, pid)` returns a QueryResult.
        stream=True:  `async for token in client.query(q, pid, stream=True)` yields answer tokens.
        """
        if stream:
            return self._stream_query(query, pipeline_id)
        return self._query(query, pipeline_id)

    async def _query(self, query: str, pipeline_id: str | None) -> QueryResult:
        r = await self._request(
            "POST", "/query", json={"query": query, "pipeline_id": pipeline_id, "stream": False}
        )
        self._check(r)
        body = r.json()
        if body.get("status") == "failed":
            raise NeuroFlowError(body.get("error", "query failed"))
        self.last_run_id = body["run_id"]
        return QueryResult(body["run_id"], body.get("response", ""), body.get("citations", []))

    async def _stream_query(self, query: str, pipeline_id: str | None) -> AsyncIterator[str]:
        r = await self._request(
            "POST", "/query", json={"query": query, "pipeline_id": pipeline_id, "stream": True}
        )
        self._check(r)
        run_id = r.json()["run_id"]
        self.last_run_id = run_id
        async with self._http.stream(
            "GET", f"/query/{run_id}/stream", headers=await self._auth_headers()
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                raise NeuroFlowError(f"{resp.status_code}: {resp.text[:300]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if event["type"] == "token":
                    yield event["delta"]
                elif event["type"] == "error":
                    raise NeuroFlowError(event["message"])
                elif event["type"] == "done":
                    return

    # ---- evaluation ----
    async def get_evaluation(
        self, run_id: str, wait: bool = True, timeout: float = 180.0, poll: float = 3.0
    ) -> EvaluationResult:
        """Get evaluation results for a query run. Evaluation runs asynchronously after the answer."""
        deadline = time.monotonic() + timeout
        while True:
            r = await self._request("GET", f"/evaluations/{run_id}")
            if r.status_code == 200:
                b = r.json()
                return EvaluationResult(
                    run_id, b.get("faithfulness"), b.get("answer_relevance"),
                    b.get("context_precision"), b.get("context_recall"), b.get("overall_score"),
                )
            if r.status_code != 404:
                self._check(r)
            if not wait or time.monotonic() > deadline:
                raise NeuroFlowError(f"No evaluation yet for run {run_id}")
            await asyncio.sleep(poll)

    # ---- pipelines ----
    async def list_pipelines(self) -> list[dict]:
        r = await self._request("GET", "/pipelines")
        self._check(r)
        return r.json()

    async def create_pipeline(self, config: dict) -> dict:
        r = await self._request("POST", "/pipelines", json=config)
        self._check(r)
        return r.json()