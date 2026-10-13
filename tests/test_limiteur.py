from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import limits, main


def make_request(ip: str) -> Request:
    return Request({"type": "http", "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 1)})


def check_chat(request: Request) -> None:
    with limits.chat_quota(request) as quota:
        quota.confirm()


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(limits, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(limits, "_hits", {})
    monkeypatch.setattr(limits, "_last_sweep", 0.0)
    monkeypatch.setattr(limits, "_global_chat_count", 0)
    return now


def test_idle_ips_are_forgotten(clock):
    for i in range(500):
        limits.check_search(make_request(f"10.0.{i // 256}.{i % 256}"))
        check_chat(make_request(f"10.1.{i // 256}.{i % 256}"))
    clock[0] += 86401
    limits.check_search(make_request("192.168.0.1"))
    assert len(limits._hits) == 1


def test_rejected_requests_leave_no_entry(monkeypatch):
    monkeypatch.setattr(limits, "SEARCH_PER_MINUTE", 0)
    monkeypatch.setattr(limits, "CHAT_PER_MINUTE", 0)
    for i in range(100):
        for check in (limits.check_search, check_chat):
            with pytest.raises(HTTPException):
                check(make_request(f"10.0.0.{i}"))
    assert limits._hits == {}


def test_limit_still_applies(clock):
    for _ in range(limits.CHAT_PER_MINUTE):
        check_chat(make_request("10.0.0.1"))
    with pytest.raises(HTTPException):
        check_chat(make_request("10.0.0.1"))
    check_chat(make_request("10.0.0.2"))
    clock[0] += 61
    check_chat(make_request("10.0.0.1"))


def test_ipv6_addresses_of_one_64_share_a_bucket():
    for i in range(limits.CHAT_PER_MINUTE):
        check_chat(make_request(f"2001:db8:1:2::{i + 1:x}"))
    with pytest.raises(HTTPException):
        check_chat(make_request("2001:db8:1:2:aaaa:bbbb:cccc:dddd"))
    check_chat(make_request("2001:db8:1:3::1"))


def test_ipv4_unchanged_and_mapped_ipv4_not_collapsed():
    assert limits.client_ip(make_request("203.0.113.7")) == "203.0.113.7"
    assert limits.client_ip(make_request("::ffff:203.0.113.7")) == "203.0.113.7"
    assert limits.client_ip(make_request("not-an-ip")) == "not-an-ip"


CHUNK = {
    "page_title": "T", "section": "S", "paragraph": 1, "url": "https://x.test/a",
    "score": 1.0, "text": "texte", "retrieval": "lexical",
}


def mistral(reply=None):
    def complete(**kwargs):
        if reply is None:
            raise RuntimeError("panne")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply), finish_reason="stop")]
        )

    return SimpleNamespace(chat=SimpleNamespace(complete=complete))


def quota_used():
    minute = sum(len(v) for k, v in limits._hits.items() if k[1:] == ("chat", 60))
    day = sum(len(v) for k, v in limits._hits.items() if k[1:] == ("chat", 86400))
    return limits._global_chat_count, minute, day


@pytest.mark.parametrize(
    ("question", "chunks", "client", "status", "used"),
    [
        ("Que propose-t-il ?", [CHUNK], mistral("Réponse"), 200, (1, 1, 1)),
        ("Que propose-t-il ?", [CHUNK], mistral(None), 502, (0, 0, 0)),
        ("Que propose-t-il ?", [CHUNK], None, 503, (0, 0, 0)),
        ("Que propose-t-il ?", [], mistral("Réponse"), 200, (0, 0, 0)),
        ("      ", [CHUNK], mistral("Réponse"), 422, (0, 0, 0)),
        ("  ab  ", [CHUNK], mistral("Réponse"), 422, (0, 0, 0)),
    ],
)
def test_chat_quota_only_counts_completions(monkeypatch, question, chunks, client, status, used):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(main, "search", lambda q, top_k=8: chunks)
    if client:
        monkeypatch.setenv("MISTRAL_API_KEY", "cle")
        monkeypatch.setattr(main, "mistral_client", lambda: client)
    response = TestClient(main.app).post("/api/chat", json={"question": question})
    assert response.status_code == status
    assert quota_used() == used


@pytest.mark.parametrize("setting", ["CHAT_GLOBAL_PER_DAY", "CHAT_PER_DAY"])
def test_quota_messages_typography(monkeypatch, setting):
    monkeypatch.setattr(limits, setting, 0)
    with pytest.raises(HTTPException) as exc:
        check_chat(make_request("10.0.0.1"))
    detail = exc.value.detail
    assert "'" not in detail
    assert "«\u00a0Chercher\u00a0»" in detail
    assert ("dernières 24 heures" in detail) == (setting == "CHAT_PER_DAY")
