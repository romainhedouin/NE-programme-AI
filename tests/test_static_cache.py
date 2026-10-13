from fastapi.testclient import TestClient

from app import main

GZIP = {"Accept-Encoding": "gzip"}


def front_client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "assets" / "index-abc123.js").write_text("x" * 5000)
    (dist / "favicon-32.png").write_bytes(b"x" * 5000)
    monkeypatch.setattr(main, "DIST_DIR", dist)
    routes = [r for r in main.app.router.routes if getattr(r, "name", None) != "assets"]
    monkeypatch.setattr(main.app.router, "routes", routes)
    main.app.mount("/assets", main.HashedAssets(directory=dist / "assets"), name="assets")
    return TestClient(main.app, follow_redirects=False)


def test_front_compresse_et_cache(tmp_path, monkeypatch):
    client = front_client(tmp_path, monkeypatch)

    asset = client.get("/assets/index-abc123.js", headers=GZIP)
    assert asset.headers["content-encoding"] == "gzip"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert asset.text == "x" * 5000

    revalidated = client.get("/assets/index-abc123.js", headers={"If-None-Match": asset.headers["etag"]})
    assert revalidated.status_code == 304
    assert revalidated.headers["cache-control"] == "public, max-age=31536000, immutable"

    assert client.get("/", headers=GZIP).headers["cache-control"] == "no-cache"
    assert client.get("/favicon-32.png").headers["cache-control"] == "public, max-age=86400"
    assert client.get("/assets/absent.js").status_code == 404


def test_api_et_liens_courts_inchanges(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    client = TestClient(main.app, follow_redirects=False)

    health = client.get("/api/health")
    assert health.status_code == 200 and "cache-control" not in health.headers

    search = client.post("/api/search", json={"question": "sécurité"}, headers=GZIP)
    assert search.status_code == 200
    assert search.headers["content-encoding"] == "gzip"
    assert search.json()["count"] > 0

    assert client.get(f"/s/{next(iter(main.short_links()))}").status_code == 302
    assert client.get("/s/zzzzzz").status_code == 404
