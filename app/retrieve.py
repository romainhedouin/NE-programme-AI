"""Recherche hybride : lexical + embeddings Mistral (si disponibles)."""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "programme.json"
EMBED_NPZ = ROOT / "data" / "embeddings.npz"
EMBED_META = ROOT / "data" / "embeddings_meta.json"

load_dotenv(ROOT / ".env", override=True)

STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "au", "aux", "et", "ou",
    "en", "dans", "sur", "pour", "par", "avec", "sans", "que", "qui", "quoi",
    "dont", "est", "sont", "a", "à", "ce", "ces", "son", "sa", "ses", "leur",
    "leurs", "il", "elle", "ils", "elles", "nous", "vous", "je", "tu", "y",
    "ne", "pas", "plus", "moins", "très", "tres", "d", "l", "n", "s", "c",
    "se", "si", "comme", "être", "etre", "avoir", "fait", "faire", "peut",
    "quel", "quelle", "quels", "quelles", "comment", "pourquoi", "quand",
    "david", "lisnard",
    # Tournures de question : présentes dans des dizaines de titres
    # (« Quel candidat propose… »), elles noient les vrais mots-clés.
    "propose", "proposer", "proposition", "propositions", "candidat", "pense",
    "veut",
    # Sens de la mesure (hausse / baisse) : c'est le sujet qui doit guider la
    # recherche ; « augmenter les impôts » attirait sinon « augmenter les salaires ».
    "augmenter", "augmente", "augmentation", "baisser", "baisse", "hausse",
}

# Sigles → forme longue. Le texte long est ramené au sigle pour le lexical,
# et la requête est enrichie de la forme longue pour les embeddings.
ACRONYMS = {
    "ia": "intelligence artificielle",
}
PHRASE_TO_ACRONYM = {
    "intelligences artificielles": "ia",
    "intelligence artificielle": "ia",
}

# Sections de navigation (listes de liens), sans contenu programmatique.
NOISE_SECTION_PREFIXES = (
    "questions voisines",
    "les dernieres actualites",
)

RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    text = strip_accents(text.lower())
    for phrase, acronym in PHRASE_TO_ACRONYM.items():
        text = text.replace(phrase, f" {acronym} ")
    tokens = re.findall(r"[a-z0-9]{2,}", text)
    return [t for t in tokens if t not in STOPWORDS]


def expand_query(query: str) -> str:
    """Ajoute la forme longue des sigles (« l'IA » → « l'IA (intelligence artificielle) »)."""
    for acronym, full in ACRONYMS.items():
        query = re.sub(
            rf"\b{acronym}\b", lambda m: f"{m.group(0)} ({full})", query, flags=re.IGNORECASE
        )
    return query


def is_noise(chunk: dict) -> bool:
    section = strip_accents(chunk["section"].lower())
    return section.startswith(NOISE_SECTION_PREFIXES)


@lru_cache(maxsize=1)
def load_corpus() -> dict:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Corpus introuvable : {DATA_PATH}. Lancez d'abord "
            "`python scripts/scrape_programme.py`."
        )
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


_embeddings_cache: dict | None = None
_embeddings_mtime: float | None = None


def load_embeddings() -> dict | None:
    global _embeddings_cache, _embeddings_mtime
    if not EMBED_NPZ.exists():
        _embeddings_cache = None
        _embeddings_mtime = None
        return None
    mtime = EMBED_NPZ.stat().st_mtime
    if _embeddings_cache is not None and _embeddings_mtime == mtime:
        return _embeddings_cache
    data = np.load(EMBED_NPZ, allow_pickle=False)
    ids = [str(x) for x in data["ids"].tolist()]
    vectors = data["vectors"].astype(np.float32)
    meta = {}
    if EMBED_META.exists():
        meta = json.loads(EMBED_META.read_text(encoding="utf-8"))
    _embeddings_cache = {
        "ids": ids,
        "vectors": vectors,
        "meta": meta,
        "id_to_row": {i: n for n, i in enumerate(ids)},
    }
    _embeddings_mtime = mtime
    return _embeddings_cache


def embeddings_status() -> dict:
    emb = load_embeddings()
    if not emb:
        return {"ready": False, "chunk_count": 0, "model": None}
    return {
        "ready": True,
        "chunk_count": len(emb["ids"]),
        "model": emb["meta"].get("model", "mistral-embed"),
        "dim": emb["meta"].get("dim"),
        "created_at": emb["meta"].get("created_at"),
    }


@lru_cache(maxsize=1)
def _lexical_index() -> dict:
    """Index BM25 : tf par passage, idf par terme (passages de navigation exclus)."""
    docs = []
    df: dict[str, int] = {}
    for chunk in load_corpus()["chunks"]:
        if is_noise(chunk):
            continue
        tokens = tokenize(f"{chunk['page_title']} {chunk['section']} {chunk['text']}")
        if not tokens:
            continue
        tf = Counter(tokens)
        title_tokens = set(tokenize(f"{chunk['page_title']} {chunk['section']}"))
        docs.append((chunk["id"], tf, len(tokens), title_tokens))
        for t in tf:
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
    avg_len = sum(d[2] for d in docs) / n if n else 1.0
    return {"docs": docs, "idf": idf, "avg_len": avg_len}


def _lexical_ranked(query: str) -> list[tuple[str, float]]:
    """BM25 : un terme rare (« ia ») pèse bien plus qu'un terme fréquent."""
    index = _lexical_index()
    idf = index["idf"]
    q_tokens = list(dict.fromkeys(tokenize(query)))
    if not q_tokens:
        return []

    # Variantes par préfixe (« nucleaire » ↔ « nucleaires »), pondérées à 0.6
    variants: dict[str, dict[str, float]] = {}
    for qt in q_tokens:
        v = {qt: 1.0} if qt in idf else {}
        if len(qt) >= 4:
            for t in idf:
                if t != qt and len(t) >= 4 and (t.startswith(qt) or qt.startswith(t)):
                    v[t] = 0.6
        variants[qt] = v

    scored: list[tuple[str, float]] = []
    for cid, tf, length, title_tokens in index["docs"]:
        norm = BM25_K1 * (1 - BM25_B + BM25_B * length / index["avg_len"])
        score = 0.0
        for qt in q_tokens:
            best = 0.0
            for t, weight in variants[qt].items():
                if t in tf:
                    sat = tf[t] * (BM25_K1 + 1) / (tf[t] + norm)
                    gain = weight * idf[t] * sat
                    if t in title_tokens:
                        gain += 0.5 * weight * idf[t]
                    best = max(best, gain)
            score += best
        if score > 0:
            scored.append((cid, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


@lru_cache(maxsize=512)
def _embed_text(model: str, text: str) -> np.ndarray | None:
    """Embedding d'une requête, mis en cache : une même question ne coûte qu'une fois."""
    from mistralai.client import Mistral

    client = Mistral(api_key=os.getenv("MISTRAL_API_KEY", "").strip())
    resp = client.embeddings.create(model=model, inputs=[text])
    vec = np.asarray(resp.data[0].embedding, dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm < 1e-12:
        return None
    return vec / norm


def _embed_query(query: str) -> np.ndarray | None:
    emb = load_embeddings()
    if not emb:
        return None
    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_"):
        return None

    model = os.getenv("MISTRAL_EMBED_MODEL", emb["meta"].get("model", "mistral-embed"))
    return _embed_text(model, expand_query(query).strip())


def _semantic_ranked(query: str) -> list[tuple[str, float]]:
    emb = load_embeddings()
    if not emb:
        return []
    try:
        qvec = _embed_query(query)
    except Exception as exc:  # noqa: BLE001
        # Mistral indisponible : on retombe sur la recherche lexicale seule
        print(f"Embedding de la requête impossible, repli lexical : {exc}")
        return []
    if qvec is None:
        return []
    sims = emb["vectors"] @ qvec  # vectors are L2-normalized
    order = np.argsort(-sims)
    by_id = _chunks_by_id()
    return [
        (emb["ids"][i], float(sims[i]))
        for i in order
        if emb["ids"][i] in by_id and not is_noise(by_id[emb["ids"][i]])
    ]


def _rrf(
    lexical: list[tuple[str, float]],
    semantic: list[tuple[str, float]],
    top_k: int,
) -> list[tuple[str, float, dict]]:
    """Reciprocal Rank Fusion — combine les classements lexical + sémantique."""
    scores: dict[str, float] = {}
    details: dict[str, dict] = {}

    for rank, (cid, raw) in enumerate(lexical):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        details.setdefault(cid, {})["lexical"] = raw
        details[cid]["lex_rank"] = rank + 1

    for rank, (cid, raw) in enumerate(semantic):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        details.setdefault(cid, {})["semantic"] = raw
        details[cid]["sem_rank"] = rank + 1

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(cid, score, details.get(cid, {})) for cid, score in ranked[:top_k]]


def _chunks_by_id() -> dict[str, dict]:
    corpus = load_corpus()
    return {c["id"]: c for c in corpus["chunks"]}


def search(
    query: str,
    top_k: int = 8,
    min_score: float = 0.0,
    min_semantic: float = 0.35,
) -> list[dict]:
    """Recherche hybride. Retombe sur lexical seul si pas d'embeddings / clé."""
    query = query.strip()
    if len(query) < 2:
        return []

    lexical = _lexical_ranked(query)
    semantic = _semantic_ranked(query)
    mode = "hybrid" if semantic and lexical else ("semantic" if semantic else "lexical")

    by_id = _chunks_by_id()
    results: list[dict] = []

    if mode == "hybrid":
        fused = _rrf(lexical, semantic, top_k=max(top_k * 3, 24))
        for cid, rrf_score, detail in fused:
            chunk = by_id.get(cid)
            if not chunk:
                continue
            sem = detail.get("semantic")
            # Filtre anti-bruit : si sémantique très faible et lexical absent, skip
            if sem is not None and sem < min_semantic and "lexical" not in detail:
                continue
            item = dict(chunk)
            item["score"] = round(rrf_score, 5)
            item["score_lexical"] = round(detail["lexical"], 3) if "lexical" in detail else None
            item["score_semantic"] = round(sem, 4) if sem is not None else None
            item["retrieval"] = mode
            results.append(item)
            if len(results) >= top_k:
                break
    elif mode == "semantic":
        for cid, sim in semantic[: top_k * 2]:
            if sim < min_semantic:
                continue
            chunk = by_id.get(cid)
            if not chunk:
                continue
            item = dict(chunk)
            item["score"] = round(sim, 4)
            item["score_lexical"] = None
            item["score_semantic"] = round(sim, 4)
            item["retrieval"] = mode
            results.append(item)
            if len(results) >= top_k:
                break
    else:
        # lexical seul (comportement MVP)
        for cid, score in lexical:
            if score < max(min_score, 1.5):
                continue
            chunk = by_id.get(cid)
            if not chunk:
                continue
            item = dict(chunk)
            item["score"] = round(score, 3)
            item["score_lexical"] = round(score, 3)
            item["score_semantic"] = None
            item["retrieval"] = mode
            results.append(item)
            if len(results) >= top_k:
                break

    return results
