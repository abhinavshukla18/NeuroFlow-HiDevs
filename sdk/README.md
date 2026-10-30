# NeuroFlow Python SDK

```python
import asyncio
from neuroflow import NeuroFlowClient

async def main():
    async with NeuroFlowClient("http://localhost:8000", "admin-client:YOUR_SECRET") as nf:
        doc = await nf.ingest_file("paper.pdf")                      # waits until ingestion completes
        pipeline = (await nf.list_pipelines())[0]["id"]
        async for token in nf.query("What is the main idea?", pipeline, stream=True):
            print(token, end="", flush=True)                         # tokens arrive as they are generated
        print(await nf.get_evaluation(nf.last_run_id))               # faithfulness, relevance, ...

asyncio.run(main())
```

Install: `pip install ./sdk`. `api_key` is either a bearer token or `client_id:client_secret`.
Requests that hit a rate limit (429) are retried automatically with exponential backoff.