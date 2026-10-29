from __future__ import annotations

from app.embed import EMBEDDING_DIMS, MODEL_NAME, BgeM3Embedder
from lingua_ids import EMBEDDING_DIMS as SHARED_DIMS
from lingua_ids import EMBEDDING_MODEL_NAME


class _FakeModel:
    def encode(self, texts, **kwargs):  # noqa: ANN001, ANN003
        del kwargs
        return {
            "dense_vecs": [[float(i)] * EMBEDDING_DIMS for i, _ in enumerate(texts)]
        }


def test_embedder_pin_matches_shared_sot() -> None:
    assert MODEL_NAME == EMBEDDING_MODEL_NAME
    assert EMBEDDING_DIMS == SHARED_DIMS
    assert SHARED_DIMS == 1024
    assert EMBEDDING_MODEL_NAME.endswith("bge-m3")
    embedder = BgeM3Embedder()
    assert embedder.model_name == EMBEDDING_MODEL_NAME
    assert embedder.dims == SHARED_DIMS


def test_bge_m3_embedder_stamps_dims(monkeypatch) -> None:  # noqa: ANN001
    embedder = BgeM3Embedder()
    monkeypatch.setattr(embedder, "_load", lambda: _FakeModel())
    vectors = embedder.embed(["a", "b"])
    assert embedder.model_name == MODEL_NAME
    assert embedder.dims == EMBEDDING_DIMS
    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIMS for v in vectors)


def test_bge_m3_rejects_wrong_dims(monkeypatch) -> None:  # noqa: ANN001
    class Bad:
        def encode(self, texts, **kwargs):  # noqa: ANN001, ANN003
            del texts, kwargs
            return {"dense_vecs": [[1.0, 2.0]]}

    embedder = BgeM3Embedder()
    monkeypatch.setattr(embedder, "_load", lambda: Bad())
    try:
        embedder.embed(["x"])
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "1024" in str(exc)
