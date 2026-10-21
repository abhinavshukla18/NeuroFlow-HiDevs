FROM ghcr.io/mlflow/mlflow:latest

# The base image has no Postgres driver, which MLflow needs for its backend store.
RUN pip install --no-cache-dir psycopg2-binary