from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main

TAIL = "citation située bien après le deux cent quatre-vingtième caractère."
CHUNK = {
    "page_title": "Logement",
    "section": "Propositions",
    "paragraph": 1,
    "url": "https://example.test/logement",
    "score": 1.0,
    "text": "Début du passage. " + "mot " * 100 + TAIL,
}


class FakeMistral:
    class chat:
        @staticmethod
        def complete(**_kwargs):
            message = SimpleNamespace(content="Réponse. [1]")
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def client(monkeypatch):
    monkeypatch.setattr(main, "search", lambda *_a, **_k: [{**CHUNK, "retrieval": "lexical"}])
    monkeypatch.setattr(main, "mistral_client", lambda: FakeMistral())
    return TestClient(main.app)


def test_chat_renvoie_le_passage_complet(monkeypatch):
    assert len(CHUNK["text"]) > 280
    sources = client(monkeypatch).post("/api/chat", json={"question": "logement ?"}).json()["sources"]
    assert sources[0]["excerpt"] == CHUNK["text"]


def test_search_renvoie_le_passage_complet(monkeypatch):
    results = client(monkeypatch).post("/api/search", json={"question": "logement ?"}).json()["results"]
    assert TAIL in results[0]["excerpt"]
