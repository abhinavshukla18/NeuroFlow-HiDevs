-- Runs once, on first startup of an empty Postgres volume.
-- MLflow stores its experiment data in its own database.
CREATE DATABASE mlflow;