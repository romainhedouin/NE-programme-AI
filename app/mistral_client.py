"""Client Mistral partagé : un seul client HTTP, connexions réutilisées entre les requêtes."""

from __future__ import annotations

from functools import lru_cache

from mistralai.client import Mistral

TIMEOUT_MS = 20_000


@lru_cache(maxsize=1)
def shared_client(api_key: str) -> Mistral:
    return Mistral(api_key=api_key, timeout_ms=TIMEOUT_MS)
