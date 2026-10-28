FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    TORCH_DEVICE=cpu \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# CPU torch first (Marker pulls torch; keep image off CUDA wheels).
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch

COPY pyproject.toml ./
COPY ingest ./ingest
COPY main.py ./
COPY docs ./docs

RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    .

CMD ["python", "main.py"]
