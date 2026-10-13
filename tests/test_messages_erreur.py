import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main

CHUNK = {
    "page_title": "Titre",
    "section": "Section",
    "paragraph": 1,
    "url": "https://example.org/page",
    "score": 1.0,
    "text": "Texte du programme.",
    "retrieval": "lexical",
}

client = TestClient(main.app, raise_server_exceptions=False)


def assert_visiteur(text: str) -> None:
    for interdit in ("{exc}", ".env", "/Users", "/private", "MISTRAL_API_KEY", "quota"):
        assert interdit not in text


class _Echec:
    class chat:
        @staticmethod
        def complete(**_):
            raise RuntimeError("429 quota exceeded for key /Users/x/.env")


def test_chat_erreur_mistral_generique(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-de-test")
    monkeypatch.setattr(main, "search", lambda *a, **k: [CHUNK])
    monkeypatch.setattr(main, "Mistral", lambda api_key: _Echec())
    res = client.post("/api/chat", json={"question": "Quel est le programme ?"})
    assert res.status_code == 502
    assert_visiteur(res.json()["detail"])
    assert "Mistral" not in res.json()["detail"]


def test_chat_cle_absente_message_visiteur(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    monkeypatch.setattr(main, "search", lambda *a, **k: [CHUNK])
    res = client.post("/api/chat", json={"question": "Quel est le programme ?"})
    assert res.status_code == 503
    assert_visiteur(res.json()["detail"])
    assert chr(160) in res.json()["detail"]


def test_health_corpus_absent_sans_chemin(monkeypatch):
    def absent():
        raise FileNotFoundError(
            "Corpus introuvable : /Users/x/data/programme.json. "
            "Lancez `python scripts/scrape_programme.py`."
        )

    monkeypatch.setattr(main, "load_corpus", absent)
    body = client.get("/api/health").json()
    assert body["ok"] is False
    assert isinstance(body["error"], str) and body["error"]
    assert "/" not in body["error"] and "python" not in body["error"]


@pytest.mark.parametrize(
    "path",
    ["/%00", "/a%00b", "/%2e%2e", "/%2f", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt"],
)
def test_public_file_404(monkeypatch, tmp_path, path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (tmp_path / "secret.txt").write_text("secret")
    monkeypatch.setattr(main, "DIST_DIR", dist)
    assert client.get(path).status_code == 404


def test_public_file_dossier_parent(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DIST_DIR", tmp_path / "dist")
    with pytest.raises(HTTPException) as exc:
        main.public_file("..")
    assert exc.value.status_code == 404


def test_public_file_sert_les_fichiers_du_build(monkeypatch, tmp_path):
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(main, "DIST_DIR", tmp_path)
    assert client.get("/favicon.svg").status_code == 200
