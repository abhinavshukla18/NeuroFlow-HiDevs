import pytest
from pydantic import ValidationError

from models.pipeline import PipelineConfig


def test_defaults_are_valid():
    cfg = PipelineConfig(name="demo")
    assert cfg.retrieval.top_k_after_rerank == 10
    assert cfg.ingestion.chunking_strategy == "auto"
    assert cfg.evaluation.auto_evaluate is True


def test_name_is_required():
    with pytest.raises(ValidationError):
        PipelineConfig()


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_name_length_limits(name):
    with pytest.raises(ValidationError):
        PipelineConfig(name=name)


def test_unknown_top_level_field_rejected():
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", bogus=1)


def test_unknown_nested_field_rejected():
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", retrieval={"bogus": 1})


@pytest.mark.parametrize("value", [0, 51])
def test_top_k_after_rerank_out_of_range(value):
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", retrieval={"top_k_after_rerank": value})


def test_temperature_out_of_range():
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", generation={"temperature": 3})


def test_chunk_size_below_minimum():
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", ingestion={"chunk_size_tokens": 63})


def test_invalid_literal_rejected():
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", ingestion={"chunking_strategy": "bogus"})
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", retrieval={"reranker": "bogus"})


def test_max_cost_must_be_positive():
    with pytest.raises(ValidationError):
        PipelineConfig(name="demo", generation={"model_routing": {"max_cost_per_call": 0}})


def test_valid_custom_config_accepted():
    cfg = PipelineConfig(name="demo", retrieval={"top_k_after_rerank": 5, "reranker": "none"})
    assert cfg.retrieval.top_k_after_rerank == 5
    assert cfg.retrieval.reranker == "none"