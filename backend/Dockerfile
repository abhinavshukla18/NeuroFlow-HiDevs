# Stage 1: dependencies
FROM python:3.12-slim AS deps
WORKDIR /app
COPY backend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 10 --prefix=/install -r requirements.txt

# Stage 2: runtime (minimal, non-root)
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r neuroflow && useradd -r -g neuroflow neuroflow
WORKDIR /app
COPY --from=deps /install /usr/local
COPY backend/ .
COPY pipelines/ ./pipelines/
COPY evaluation/ ./evaluation/
RUN mkdir -p /data/uploads /data/models \
    && chown -R neuroflow:neuroflow /app /data
USER neuroflow
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]