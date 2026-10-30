from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestionConfig(Strict):
    chunking_strategy: Literal["fixed_size", "semantic", "hierarchical", "auto"] = "auto"
    chunk_size_tokens: int = Field(512, ge=64, le=2048)
    chunk_overlap_tokens: int = Field(64, ge=0, le=512)
    extractors_enabled: list[Literal["pdf", "docx", "image", "csv", "url"]] = ["pdf", "docx", "image", "csv", "url"]


class RetrievalConfig(Strict):
    dense_k: int = Field(20, ge=1, le=200)
    sparse_k: int = Field(20, ge=1, le=200)
    reranker: Literal["cross-encoder", "none"] = "cross-encoder"
    top_k_after_rerank: int = Field(10, ge=1, le=50)
    query_expansion: bool = True
    metadata_filters_enabled: bool = True
    ef_search: int = Field(40, ge=10, le=400)
    rrf_k: int = Field(60, ge=1, le=200)


class ModelRouting(Strict):
    task_type: str = "rag_generation"
    max_cost_per_call: float | None = Field(None, gt=0)


class GenerationConfig(Strict):
    model_routing: ModelRouting = ModelRouting()
    max_context_tokens: int = Field(4000, ge=500, le=32000)
    temperature: float = Field(0.2, ge=0, le=2)
    system_prompt_variant: Literal["default", "precise", "concise"] = "default"


class EvaluationConfig(Strict):
    auto_evaluate: bool = True
    training_threshold: float = Field(0.8, ge=0, le=1)


class PipelineConfig(Strict):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    ingestion: IngestionConfig = IngestionConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    generation: GenerationConfig = GenerationConfig()
    evaluation: EvaluationConfig = EvaluationConfig()

    @classmethod
    def from_row(cls, name: str, description: str | None, config: dict) -> "PipelineConfig":
        return cls(**{**config, "name": name, "description": description})

    def stored(self) -> dict:
        return self.model_dump(exclude={"name", "description"})