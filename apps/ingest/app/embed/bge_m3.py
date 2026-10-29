from __future__ import annotations

import logging
import os
from typing import Protocol

from lingua_ids import EMBEDDING_DIMS, EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

# Re-exports of the shared AD-12 pin (SoT lives in lingua_ids).
MODEL_NAME = EMBEDDING_MODEL_NAME


class Embedder(Protocol):
    """Seam for dense embeddings (mockable in unit tests)."""

    @property
    def model_name(self) -> str: ...

    @property
    def dims(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3Embedder:
    """Local BGE-M3 dense vectors via FlagEmbedding at the shared AD-12 dims."""

    def __init__(
        self,
        *,
        model_name: str = MODEL_NAME,
        use_fp16: bool | None = None,
    ) -> None:
        self._model_name = model_name
        if use_fp16 is None:
            # CPU Compose default: fp32 for stability; override with EMBED_FP16=1.
            use_fp16 = os.environ.get("EMBED_FP16", "").strip() in {
                "1",
                "true",
                "yes",
            }
        self._use_fp16 = use_fp16
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dims(self) -> int:
        return EMBEDDING_DIMS

    def _load(self):
        if self._model is not None:
            return self._model
        # FlagEmbedding==1.4.2 (pinned in pyproject / Implementation Notes).
        from FlagEmbedding import BGEM3FlagModel

        logger.info(
            "Loading FlagEmbedding BGEM3FlagModel %s (fp16=%s)",
            self._model_name,
            self._use_fp16,
        )
        self._model = BGEM3FlagModel(self._model_name, use_fp16=self._use_fp16)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        max_length_raw = os.environ.get("EMBED_MAX_LENGTH", "").strip()
        max_length = int(max_length_raw) if max_length_raw.isdigit() else 8192
        out = model.encode(
            texts,
            batch_size=int(os.environ.get("EMBED_BATCH_SIZE", "8") or "8"),
            max_length=max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense = out["dense_vecs"]
        vectors: list[list[float]] = []
        for row in dense:
            vec = [float(x) for x in row]
            if len(vec) != EMBEDDING_DIMS:
                raise ValueError(
                    f"expected {EMBEDDING_DIMS}-dim embedding, got {len(vec)}"
                )
            vectors.append(vec)
        return vectors
