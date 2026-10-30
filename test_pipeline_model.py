from pydantic import ValidationError

from models.pipeline import PipelineConfig

ok = PipelineConfig(name="legal", retrieval={"dense_k": 30})
assert ok.retrieval.dense_k == 30 and ok.generation.temperature == 0.2
for bad in (
    {"name": "x", "unknown": 1},
    {"name": "x", "retrieval": {"dense_k": 30, "bogus": True}},
    {"name": "x", "generation": {"model_routing": {"nope": 1}}},
):
    try:
        PipelineConfig(**bad)
        raise SystemExit(f"FAIL: accepted {bad}")
    except ValidationError:
        pass
print("PASS unknown keys rejected at every level")