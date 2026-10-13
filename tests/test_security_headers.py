import pytest
from fastapi.testclient import TestClient

from app.main import app, short_links

client = TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_not_exposed(path):
    assert client.get(path).status_code == 404


def test_security_headers_on_all_kinds_of_responses():
    code = next(iter(short_links()))
    responses = [
        client.get("/api/health"),
        client.get("/"),
        client.get("/s/inconnu"),
        client.get(f"/s/{code}"),
        client.get("/introuvable.png"),
        client.post("/api/search", json={"question": "x"}),
    ]
    assert responses[3].status_code == 302
    for r in responses:
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert r.headers["x-frame-options"] == "DENY"
        csp = r.headers["content-security-policy"]
        assert "script-src 'self';" in csp
        assert "frame-ancestors 'none'" in csp
        assert "unsafe-inline" not in csp
