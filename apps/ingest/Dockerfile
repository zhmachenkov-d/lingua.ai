FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    TORCH_DEVICE=cpu \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TEXTBOOKS_DIR=/textbooks \
    LLAMA_CPP_BINARY=/usr/local/bin/llama-server \
    LD_LIBRARY_PATH=/opt/llama.cpp \
    SURYA_INFERENCE_BACKEND=llamacpp

WORKDIR /app

# Marker/Surya CPU path needs upstream llama-server (not shipped by marker-pdf).
# Pin a known ubuntu-x64 release for reproducible Compose HITL.
ARG LLAMA_CPP_RELEASE=b11946
# Tesseract/ocrmypdf = default Compose CPU OCR; llama-server kept for optional Marker.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      ghostscript \
      libgomp1 \
      ocrmypdf \
      tesseract-ocr \
      tesseract-ocr-eng \
 && curl -fsSL \
      "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_RELEASE}/llama-${LLAMA_CPP_RELEASE}-bin-ubuntu-x64.tar.gz" \
      -o /tmp/llama.cpp.tar.gz \
 && mkdir -p /opt/llama.cpp \
 && tar -xzf /tmp/llama.cpp.tar.gz -C /opt/llama.cpp --strip-components=1 \
 && ln -sf /opt/llama.cpp/llama-server /usr/local/bin/llama-server \
 && rm -f /tmp/llama.cpp.tar.gz \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Path dep is resolved by uv locally; Docker installs the shared package explicitly.
COPY packages/lingua_ids /packages/lingua_ids
COPY packages/lingua_corpus /packages/lingua_corpus
COPY apps/ingest/pyproject.toml ./
COPY apps/ingest/app ./app
COPY apps/ingest/main.py ./

# Resolve runtime deps with PyTorch CPU as primary index so torch stays CPU;
# then install this package without re-resolving deps (avoids PyPI CUDA torch).
# FlagEmbedding pulls transformers/sentence-transformers; install after torch CPU.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    "torch" \
    "torchvision" \
    "marker-pdf==2.0.0" \
    "pymupdf==1.28.2" \
    "psutil==7.2.2" \
    "sqlalchemy[asyncio]>=2,<3" \
    "psycopg[binary]>=3.2" \
    "pgvector>=0.4,<0.5" \
    "FlagEmbedding==1.4.2" \
 && pip install --no-cache-dir --no-deps /packages/lingua_ids \
 && pip install --no-cache-dir --no-deps /packages/lingua_corpus \
 && pip install --no-cache-dir --no-deps .

# Hugging Face / FlagEmbedding weights cache (Compose volume optional).
ENV HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf \
    INGEST_MODE=tracer

CMD ["python", "main.py"]
