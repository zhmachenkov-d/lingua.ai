FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    TORCH_DEVICE=cpu \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TEXTBOOKS_DIR=/textbooks

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY main.py ./

# Resolve runtime deps with PyTorch CPU as primary index so torch stays CPU;
# then install this package without re-resolving deps (avoids PyPI CUDA torch).
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    "torch" \
    "torchvision" \
    "marker-pdf==2.0.0" \
    "pymupdf==1.28.2" \
    "psutil==7.2.2" \
 && pip install --no-cache-dir --no-deps .

CMD ["python", "main.py"]
