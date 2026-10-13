"""Calcule les embeddings Mistral pour chaque passage du programme.

Incrémental : les vecteurs déjà présents dans data/embeddings.npz sont réutilisés
pour les passages dont le texte n'a pas changé. Seuls les passages nouveaux ou
modifiés sont envoyés à Mistral (aucun appel si le corpus est inchangé).

Prérequis : data/programme.json (scrape) + MISTRAL_API_KEY dans .env

Usage :
  python scripts/embed_programme.py
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from mistralai.client import Mistral

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "data" / "programme.json"
OUT_NPZ = ROOT / "data" / "embeddings.npz"
OUT_META = ROOT / "data" / "embeddings_meta.json"
BATCH_SIZE = 32
MAX_ATTEMPTS = 6  # attentes : 2, 4, 8, 16, 32 s

load_dotenv(ROOT / ".env")


def chunk_text(chunk: dict) -> str:
    return (
        f"{chunk['page_title']}\n"
        f"{chunk['section']}\n"
        f"{chunk['text']}"
    )


def embed_batch(client: Mistral, model: str, batch: list[str]):
    """Appel embeddings avec nouvelles tentatives sur erreurs passagères (429, 5xx, réseau)."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return client.embeddings.create(model=model, inputs=batch)
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None)
            transient = status is None or status == 429 or status >= 500
            if not transient or attempt == MAX_ATTEMPTS:
                raise
            delay = 2**attempt
            print(f"  erreur {status or type(exc).__name__}, nouvelle tentative dans {delay} s "
                  f"({attempt}/{MAX_ATTEMPTS - 1})")
            time.sleep(delay)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cache(model: str) -> tuple[dict[str, np.ndarray], list[str], list[str]]:
    """Vecteurs existants indexés par hash de texte (vide si autre modèle ou ancien format)."""
    if not OUT_NPZ.exists() or not OUT_META.exists():
        return {}, [], []
    meta = json.loads(OUT_META.read_text(encoding="utf-8"))
    data = np.load(OUT_NPZ, allow_pickle=False)
    if meta.get("model") != model or "hashes" not in data:
        return {}, [], []
    hashes = [str(h) for h in data["hashes"]]
    ids = [str(i) for i in data["ids"]]
    return dict(zip(hashes, data["vectors"])), ids, hashes


def main() -> None:
    model = os.getenv("MISTRAL_EMBED_MODEL", "mistral-embed")
    if not CORPUS_PATH.exists():
        raise SystemExit(
            f"Corpus introuvable : {CORPUS_PATH}. "
            "Lancez d'abord python scripts/scrape_programme.py"
        )

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    chunks = corpus["chunks"]
    texts = [chunk_text(c) for c in chunks]
    ids = [c["id"] for c in chunks]
    hashes = [text_hash(t) for t in texts]

    cache, cached_ids, cached_hashes = load_cache(model)
    if cached_ids == ids and cached_hashes == hashes:
        print(f"Embeddings à jour ({len(ids)} passages) : aucun appel à Mistral.")
        return

    todo = [i for i, h in enumerate(hashes) if h not in cache]
    print(
        f"{len(texts)} passages : {len(texts) - len(todo)} réutilisés, "
        f"{len(todo)} à calculer ({model}), lots de {BATCH_SIZE}…"
    )

    if todo:
        api_key = os.getenv("MISTRAL_API_KEY", "").strip()
        if not api_key or api_key.startswith("your_"):
            raise SystemExit("MISTRAL_API_KEY manquante dans .env")
        client = Mistral(api_key=api_key)
        for start in range(0, len(todo), BATCH_SIZE):
            batch_idx = todo[start : start + BATCH_SIZE]
            resp = embed_batch(client, model, [texts[i] for i in batch_idx])
            # SDK may return data sorted by index
            ordered = sorted(resp.data, key=lambda d: d.index)
            for i, d in zip(batch_idx, ordered):
                vec = np.asarray(d.embedding, dtype=np.float32)
                cache[hashes[i]] = vec / max(float(np.linalg.norm(vec)), 1e-12)
            print(f"  [{min(start + BATCH_SIZE, len(todo))}/{len(todo)}]")
            time.sleep(0.15)

    matrix = np.stack([cache[h] for h in hashes]).astype(np.float32)
    np.savez_compressed(
        OUT_NPZ, ids=np.asarray(ids), hashes=np.asarray(hashes), vectors=matrix
    )

    meta = {
        "model": model,
        "chunk_count": len(ids),
        "dim": int(matrix.shape[1]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_scraped_at": corpus.get("scraped_at"),
        "path": str(OUT_NPZ.name),
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit {OUT_NPZ} ({matrix.shape[0]} × {matrix.shape[1]})")
    print(f"Métadonnées : {OUT_META}")


if __name__ == "__main__":
    main()
