from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.mistral_client as mistral_client
import app.retrieve as retrieve

CHUNK = {
    "page_title": "Titre",
    "section": "Section",
    "paragraph": 1,
    "url": "https://example.org/page",
    "score": 1.0,
    "retrieval": "lexical",
    "text": "Texte du passage.",
}


@pytest.fixture
def built(monkeypatch):
    calls = []

    class FakeMistral:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = SimpleNamespace(complete=self._complete)
            self.embeddings = SimpleNamespace(create=self._create)

        @staticmethod
        def _complete(**kwargs):
            message = SimpleNamespace(content="Réponse.")
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])

        @staticmethod
        def _create(**kwargs):
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 0.0])])

    monkeypatch.setattr(mistral_client, "Mistral", FakeMistral)
    monkeypatch.setattr(main, "search", lambda question, top_k: [CHUNK])
    monkeypatch.setattr(main, "check_chat", lambda request: None)
    mistral_client.shared_client.cache_clear()
    yield calls
    mistral_client.shared_client.cache_clear()


def test_un_seul_client_pour_chat_et_embeddings(built, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-de-test")
    api = TestClient(main.app)

    for _ in range(3):
        assert api.post("/api/chat", json={"question": "Que propose le programme ?"}).status_code == 200
    for i in range(3):
        assert retrieve._embed_text("mistral-embed", f"question {i}") is not None

    assert len(built) == 1
    assert built[0]["timeout_ms"] == 20_000


def test_cle_absente_puis_definie_plus_tard(built, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    api = TestClient(main.app)

    assert api.post("/api/chat", json={"question": "Que propose le programme ?"}).status_code == 503
    assert retrieve._embed_query("Que propose le programme ?") is None
    assert built == []

    monkeypatch.setenv("MISTRAL_API_KEY", "cle-de-test")
    assert api.post("/api/chat", json={"question": "Que propose le programme ?"}).status_code == 200
    assert len(built) == 1
