"""Extrait le programme officiel Nouvelle Énergie en chunks sourcés.

Source unique autorisée :
  - https://www.unenouvelleenergie.fr/notre-programme/
  - pages /questions/ listées dans le sitemap du même site

Usage :
  python scripts/scrape_programme.py
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.unenouvelleenergie.fr"
SITEMAPS = [
    f"{BASE}/pages-sitemap.xml",
    f"{BASE}/questions-sitemap.xml",
]
ALLOWED_PREFIXES = (
    "/notre-programme",
    "/questions/",
)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "programme.json"
USER_AGENT = "programme-lisnard-bot/0.1 (+open-source; citation du programme officiel)"
MAX_ERROR_RATIO = 0.1


def norm_space(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def fetch(client: httpx.Client, url: str) -> str:
    r = client.get(url, timeout=45.0)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def sitemap_urls(client: httpx.Client) -> list[str]:
    urls: list[str] = []
    for sm in SITEMAPS:
        xml = fetch(client, sm)
        for loc in re.findall(r"<loc>(.*?)</loc>", xml):
            path = urlparse(loc).path
            if any(path.startswith(p) for p in ALLOWED_PREFIXES):
                # Skip index-only listing pages with little content
                if path.rstrip("/") in {"/questions"}:
                    continue
                urls.append(loc.rstrip("/") + "/")
    # Always include hub programme
    hub = f"{BASE}/notre-programme/"
    if hub not in urls:
        urls.insert(0, hub)
    # Dedupe keep order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def page_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return norm_space(h1.get_text(" ", strip=True))
    if soup.title and soup.title.string:
        return norm_space(soup.title.string.split("|")[0])
    return "Sans titre"


SKIP_SECTION_PREFIXES = (
    "les questions qu",
    "chacune a sa page",
    "découvrir",
    "découvrez",
    # Listes de liens (navigation), sans contenu programmatique
    "questions voisines",
    "les dernières actualités",
    "les questions, une par une",
)

# Appels à l'action et vignettes de liens, sans contenu programmatique
BOILERPLATE_RE = re.compile(
    r"^(?:(?:le sujet en entier|pour approfondir)\s*:.{0,60}|.+\bdécouvrir\s*→)$",
    re.IGNORECASE,
)
LINK_LABEL_RE = re.compile(r"\s*·\s*voir l[’']intervention\s*$", re.IGNORECASE)
ATTRIBUTION_RE = re.compile(r"^(?:D[’']après|Élément de contexte)\b")


def is_boilerplate(text: str) -> bool:
    return bool(BOILERPLATE_RE.match(text))


def strip_link_label(text: str) -> str:
    return LINK_LABEL_RE.sub("", text)


def drop_duplicates(chunks: list[dict], seen: set[str]) -> list[dict]:
    """Écarte les passages déjà vus sur une autre page ; les mentions de source restent."""
    kept = []
    for chunk in chunks:
        if not ATTRIBUTION_RE.match(chunk["text"]):
            if chunk["text"] in seen:
                continue
            seen.add(chunk["text"])
        kept.append(chunk)
    return kept


def extract_chunks(url: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    title = page_title(soup)
    main = soup.find("main") or soup.body or soup
    for tag in main.find_all(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    # Keep headings; remove chrome-only headers after title is known
    for tag in main.find_all("header"):
        # Preserve h1–h4 inside header for section tracking, drop the rest
        for child in list(tag.children):
            name = getattr(child, "name", None)
            if name not in {"h1", "h2", "h3", "h4"} and name is not None:
                if hasattr(child, "decompose"):
                    child.decompose()

    path = urlparse(url).path
    kind = "programme" if path.startswith("/notre-programme") else "questions"

    chunks: list[dict] = []
    current_section = title
    paragraph_index = 0
    skip_mode = False

    blocks = main.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"])
    for el in blocks:
        text = norm_space(el.get_text(" ", strip=True))
        if not text:
            continue

        lower = text.lower()
        if el.name in {"h1", "h2", "h3", "h4"}:
            current_section = text
            skip_mode = any(lower.startswith(p) for p in SKIP_SECTION_PREFIXES)
            continue

        if skip_mode or any(lower.startswith(p) for p in SKIP_SECTION_PREFIXES):
            continue
        if len(text) < 40 or is_boilerplate(text):
            continue

        paragraph_index += 1
        chunks.append(
            {
                "id": f"{kind}:{path.strip('/').replace('/', '-')}:p{paragraph_index}",
                "url": url,
                "kind": kind,
                "page_title": title,
                "section": current_section,
                "paragraph": paragraph_index,
                "text": strip_link_label(text),
            }
        )
    return chunks


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr"}
    all_chunks: list[dict] = []
    pages: list[dict] = []
    seen_texts: set[str] = set()
    errors = 0

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        urls = sitemap_urls(client)
        print(f"{len(urls)} pages à extraire…")
        for i, url in enumerate(urls, 1):
            try:
                html = fetch(client, url)
                chunks = drop_duplicates(extract_chunks(url, html), seen_texts)
                all_chunks.extend(chunks)
                pages.append({"url": url, "chunks": len(chunks), "title": chunks[0]["page_title"] if chunks else ""})
                print(f"[{i}/{len(urls)}] {len(chunks):3d} chunks  {url}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(urls)}] ERREUR {url}: {exc}")
                errors += 1
            time.sleep(0.35)

    # Garde-fou : ne pas écraser le corpus existant par un corpus tronqué
    if not all_chunks or errors > MAX_ERROR_RATIO * len(urls):
        raise SystemExit(
            f"Scrape incomplet ({errors}/{len(urls)} pages en erreur, "
            f"{len(all_chunks)} chunks) : {OUT} non modifié."
        )

    payload = {
        "source": BASE,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "chunk_count": len(all_chunks),
        "pages": pages,
        "chunks": all_chunks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit {OUT} ({len(all_chunks)} chunks, {len(pages)} pages)")


if __name__ == "__main__":
    main()
