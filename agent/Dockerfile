# Agent Dockerfile — Python 3.12 + uv
#
# NOTE: Docling/docling-parse heavy ML models (~1 GB) are NOT baked in.
# They download to ~/.docling/models on the first /upload request.
# Mount a volume at /root/.docling to persist them across container restarts:
#   docker run -v docling-models:/root/.docling ...
#
# Build caveat: fastembed → onnxruntime → torch/CUDA wheel chain (~5 GB on
# first build). Requires ~8 GB free disk space in Docker and a good internet
# connection. On CI, pin fastembed to the CPU-only onnxruntime wheel or use
# a pre-built base image.
#
# System deps:
#   - build-essential / gcc: needed by some compiled Python extensions
#   - libgl1 / libglib2.0-0: required by OpenCV (pulled in by docling)
#   - libgomp1: required by LightGBM (pulled in by flashrank)

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8123

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8123"]
