"""Application settings, loaded from environment variables.

Every setting is typed and documented. In Docker, values come from the
repo's .env file (see .env.example). For local runs, a .env file in the
current directory is also read.
"""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore env vars this app does not use
    )

    # --- Postgres ---
    postgres_db: str = Field("neuroflow", description="Postgres database name.")
    postgres_user: str = Field("neuroflow", description="Postgres user.")
    postgres_password: str = Field(..., description="Postgres password. Required, no default.")
    postgres_host: str = Field("postgres", description="Postgres hostname (the compose service name).")
    postgres_port: int = Field(5432, description="Postgres port.")
    db_pool_min_size: int = Field(2, ge=1, description="Minimum connections kept open in the pool.")
    db_pool_max_size: int = Field(10, ge=1, description="Maximum connections in the pool.")

    # --- Redis ---
    redis_password: str = Field(..., description="Redis password. Required, no default.")
    redis_host: str = Field("redis", description="Redis hostname (the compose service name).")
    redis_port: int = Field(6379, description="Redis port.")

    # --- MLflow ---
    mlflow_tracking_uri: str = Field(
        "http://mlflow:5000", description="Base URL of the MLflow tracking server."
    )

    # --- OpenTelemetry / Jaeger ---
    otel_exporter_otlp_endpoint: str = Field(
        "http://jaeger:4317", description="OTLP gRPC endpoint that receives traces."
    )
    otel_service_name: str = Field(
        "neuroflow-api", description="Service name shown in the Jaeger UI."
    )

    # --- Behaviour ---
    health_check_timeout_seconds: float = Field(
        3.0, gt=0, description="Timeout for each dependency check in /health."
    )

    @property
    def postgres_dsn(self) -> str:
        """Connection string for the main database. Credentials are URL-encoded."""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Connection string for Redis. The password is URL-encoded."""
        password = quote_plus(self.redis_password)
        return f"redis://:{password}@{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them everywhere."""
    return Settings()