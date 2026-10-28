from __future__ import annotations

from app.embed import EMBEDDING_DIMS, MODEL_NAME, BgeM3Embedder


class _FakeModel:
    def encode(self, texts, **kwargs):  # noqa: ANN001, ANN003
        del kwargs
        return {
            "dense_vecs": [[float(i)] * EMBEDDING_DIMS for i, _ in enumerate(texts)]
        }


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
