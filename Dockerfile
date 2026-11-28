FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local

# Create user AND give permissions to volume mount points
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /chromadb /chromadb/uploads && \
    chown -R appuser:appuser /chromadb

USER appuser
COPY src/ ./src/
COPY pyproject.toml .
COPY docs/ ./docs/
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
