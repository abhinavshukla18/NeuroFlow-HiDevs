from tests.integration.helpers import (
    ingest_test_document, submit_query, wait_for_evaluation,
    wait_for_generation, wait_for_status,
)


async def test_full_rag_pipeline(client):
    doc = await ingest_test_document(client)
    await wait_for_status(client, doc["document_id"], "complete", timeout=60)

    run_id = await submit_query(client, "What is the main topic of the document?")
    response = await wait_for_generation(client, run_id, timeout=30)

    assert response["chunks_used"] > 0
    assert len(response["generation"]) > 50

    eval_result = await wait_for_evaluation(client, run_id, timeout=120)
    assert eval_result["overall_score"] > 0.5


async def test_deduplication(client):
    first = await ingest_test_document(client)
    second = await ingest_test_document(client)
    assert second["duplicate"] is True
    assert second["document_id"] == first["document_id"]