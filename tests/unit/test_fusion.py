from pipelines.retrieval import RetrievalResult
from pipelines.retrieval.fusion import reciprocal_rank_fusion


def r(chunk_id: str, strategy: str = "dense") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        content=f"content {chunk_id}",
        score=1.0,
        document_id="doc",
        source_name="file.txt",
        page_number=None,
        metadata={},
        strategies=[strategy],
    )


def ids(results) -> list[str]:
    return [x.chunk_id for x in results]


def test_single_list_keeps_order():
    assert ids(reciprocal_rank_fusion([[r("A"), r("B"), r("C")]])) == ["A", "B", "C"]


def test_chunk_in_two_lists_beats_chunk_in_one():
    fused = reciprocal_rank_fusion([[r("A"), r("B")], [r("A", "sparse"), r("C", "sparse")]])
    assert ids(fused)[0] == "A"


def test_consensus_across_three_lists():
    fused = reciprocal_rank_fusion([
        [r("A"), r("B")],
        [r("B", "sparse"), r("C", "sparse")],
        [r("B", "metadata"), r("A", "metadata")],
    ])
    assert ids(fused)[0] == "B"


def test_results_are_deduplicated():
    fused = reciprocal_rank_fusion([[r("A"), r("B")], [r("B", "sparse"), r("A", "sparse")]])
    assert sorted(ids(fused)) == ["A", "B"]


def test_strategies_are_merged():
    fused = reciprocal_rank_fusion([[r("A")], [r("A", "sparse")]])
    assert {"dense", "sparse"} <= set(fused[0].strategies)


def test_empty_input_returns_empty_list():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_higher_rank_wins_within_one_list():
    fused = reciprocal_rank_fusion([[r("X"), r("Y")], [r("Z", "sparse")]])
    assert ids(fused).index("X") < ids(fused).index("Y")