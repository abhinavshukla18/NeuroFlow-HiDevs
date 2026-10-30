import asyncio
import os
import sys

from neuroflow import NeuroFlowClient


async def main() -> None:
    base_url = os.getenv("NEUROFLOW_URL", "http://localhost:8000")
    api_key = os.environ["NEUROFLOW_API_KEY"]  # "client_id:client_secret"
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/test_doc.pdf"

    async with NeuroFlowClient(base_url, api_key) as nf:
        doc = await nf.ingest_file(path)
        print(f"Ingested {doc.filename}: {doc.chunk_count} chunks (duplicate={doc.duplicate})")

        pipelines = await nf.list_pipelines()
        pipeline_id = pipelines[0]["id"]

        print("Answer: ", end="")
        async for token in nf.query("What is the main topic of the document?", pipeline_id, stream=True):
            print(token, end="", flush=True)
        print()

        print(await nf.get_evaluation(nf.last_run_id))


asyncio.run(main())