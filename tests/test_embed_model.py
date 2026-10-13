import sys
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import retrieve  # noqa: E402

STORED_MODEL = "mistral-embed"
STORED_DIM = 4


@pytest.fixture
def stub_mistral(monkeypatch):
    calls = []
    out_dim = {"value": STORED_DIM}

    class FakeEmbeddings:
        def create(self, model, inputs):
            calls.append(model)
            vec = np.ones(out_dim["value"], dtype=np.float32).tolist()
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=vec)])

    class FakeMistral:
        def __init__(self, api_key=None, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("mistralai.client.Mistral", FakeMistral)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_EMBED_MODEL", "another-model")

    ids = [c["id"] for c in retrieve.load_corpus()["chunks"][:5]]
    vectors = np.full((len(ids), STORED_DIM), 0.5, dtype=np.float32)
    monkeypatch.setattr(
        retrieve,
        "load_embeddings",
        lambda: {
            "ids": ids,
            "vectors": vectors,
            "meta": {"model": STORED_MODEL, "dim": STORED_DIM},
            "id_to_row": {i: n for n, i in enumerate(ids)},
        },
    )
    retrieve._embed_text.cache_clear()
    yield calls, out_dim
    retrieve._embed_text.cache_clear()


def test_query_embedded_with_stored_model(stub_mistral):
    calls, _ = stub_mistral
    retrieve.search("intelligence artificielle")
    assert calls == [STORED_MODEL]


def test_dimension_mismatch_falls_back_to_lexical(stub_mistral):
    _, out_dim = stub_mistral
    out_dim["value"] = STORED_DIM * 2
    results = retrieve.search("intelligence artificielle")
    assert results
    assert {r["retrieval"] for r in results} == {"lexical"}
