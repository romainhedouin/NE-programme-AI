from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import limits


def make_request(ip: str) -> Request:
    return Request({"type": "http", "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 1)})


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
        limits.check_chat(make_request(f"10.1.{i // 256}.{i % 256}"))
    clock[0] += 86401
    limits.check_search(make_request("192.168.0.1"))
    assert len(limits._hits) == 1


def test_rejected_requests_leave_no_entry(monkeypatch):
    monkeypatch.setattr(limits, "SEARCH_PER_MINUTE", 0)
    monkeypatch.setattr(limits, "CHAT_PER_MINUTE", 0)
    for i in range(100):
        for check in (limits.check_search, limits.check_chat):
            with pytest.raises(HTTPException):
                check(make_request(f"10.0.0.{i}"))
    assert limits._hits == {}


def test_limit_still_applies(clock):
    for _ in range(limits.CHAT_PER_MINUTE):
        limits.check_chat(make_request("10.0.0.1"))
    with pytest.raises(HTTPException):
        limits.check_chat(make_request("10.0.0.1"))
    limits.check_chat(make_request("10.0.0.2"))
    clock[0] += 61
    limits.check_chat(make_request("10.0.0.1"))


def test_ipv6_addresses_of_one_64_share_a_bucket():
    for i in range(limits.CHAT_PER_MINUTE):
        limits.check_chat(make_request(f"2001:db8:1:2::{i + 1:x}"))
    with pytest.raises(HTTPException):
        limits.check_chat(make_request("2001:db8:1:2:aaaa:bbbb:cccc:dddd"))
    limits.check_chat(make_request("2001:db8:1:3::1"))


def test_ipv4_unchanged_and_mapped_ipv4_not_collapsed():
    assert limits.client_ip(make_request("203.0.113.7")) == "203.0.113.7"
    assert limits.client_ip(make_request("::ffff:203.0.113.7")) == "203.0.113.7"
    assert limits.client_ip(make_request("not-an-ip")) == "not-an-ip"
