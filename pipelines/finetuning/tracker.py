import os
from statistics import mean
from uuid import UUID

import mlflow
import mlflow.pyfunc

TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
EXPERIMENT_NAME = "neuroflow-finetuning"


class _FineTunedRef(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        return model_input


def _setup() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)


def start_training_job(job_id: UUID, rows, base_model: str, jsonl_path: str) -> str:
    _setup()
    dates = [r["created_at"] for r in rows]
    with mlflow.start_run(run_name=f"finetune-{job_id}") as run:
        mlflow.log_params({
            "base_model": base_model,
            "training_pair_count": len(rows),
            "avg_quality_score": round(mean(r["quality_score"] for r in rows), 4),
            "date_range": f"{min(dates).date()} to {max(dates).date()}",
        })
        mlflow.log_artifact(jsonl_path)
        return run.info.run_id


def log_job_result(run_id: str, job_id: UUID, result: dict, model_name: str) -> None:
    _setup()
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metrics({
            "training_loss": float(result.get("training_loss") or 0),
            "validation_loss": float(result.get("validation_loss") or 0),
            "training_token_count": float(result.get("trained_tokens") or 0),
        })
        mlflow.set_tags({"fine_tuned_model": model_name, "job_id": str(job_id)})
        try:
            mlflow.pyfunc.log_model(name="model", python_model=_FineTunedRef())
        except TypeError:
            mlflow.pyfunc.log_model(artifact_path="model", python_model=_FineTunedRef())
    mlflow.register_model(f"runs:/{run_id}/model", f"neuroflow-finetune-{job_id}")


def run_url(run_id: str) -> str:
    exp = mlflow.get_run(run_id).info.experiment_id
    return f"{TRACKING_URI}/#/experiments/{exp}/runs/{run_id}"