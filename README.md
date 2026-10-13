# Questions sourcées sur le programme Lisnard

Outil open source pour interroger le programme de David Lisnard **uniquement** à partir du site officiel [unenouvelleenergie.fr/notre-programme](https://www.unenouvelleenergie.fr/notre-programme/).

**Règle d’or :** chaque réponse s’appuie sur des extraits du corpus local, avec citation (page, section, paragraphe, URL). Si rien de pertinent n’est trouvé → *« Aucune réponse trouvée dans le programme officiel. »*  
Ce n’est **pas** le site officiel du parti.

Deux modes dans l’UI :
- **Demander** — RAG : recherche + réponse rédigée par Mistral avec citations
- **Chercher** — recherche seule (passages du programme, sans rédaction LLM)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Site officiel unenouvelleenergie.fr                            │
│  (/notre-programme/*  +  /questions/*)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ scrape_programme.py
                             ▼
                  data/programme.json
                             │
                             │ embed_programme.py (Mistral Embed)
                             ▼
              data/embeddings.npz  (+ meta)
                             │
                             ▼
                   app/retrieve.py (hybride)
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
        /api/search                   /api/chat
     (passages seuls)            (passages → Mistral)
              │                             │
              └──────────────┬──────────────┘
                             ▼
              frontend/ (Vue 3 — clean architecture)
              Demander | Chercher
```

### Flux

1. **Scrape** (manuel) → corpus JSON sourcé  
2. **Embed** (manuel, une fois la clé disponible) → vecteurs pré-calculés  
3. **Question / recherche** → score **hybride** (mots-clés + similarité cosinus)  
4. Mode *Demander* : top passages → Mistral chat (prompt strict)  
5. Mode *Chercher* : top passages affichés tels quels  

Sans embeddings (ou sans clé), repli automatique sur la recherche lexicale seule.

---

## Arborescence

```
projet/
├── app/                 API FastAPI + RAG
├── data/                Corpus + embeddings
├── scripts/             Scrape + embed
└── frontend/            UI Vue 3 (clean architecture)
    ├── src/domain/
    ├── src/application/
    ├── src/infrastructure/
    └── src/ui/
```

Détail du front : voir [`frontend/README.md`](frontend/README.md).

| Fichier / dossier | Rôle |
|-------------------|------|
| `app/main.py` | API `/api/health`, `/api/search`, `/api/chat` + sert `frontend/dist` |
| `app/prompts.py` | Prompt strict pour le chat |
| `app/retrieve.py` | Recherche hybride (lexical + embeddings, RRF) |
| `scripts/scrape_programme.py` | Extraction site officiel |
| `scripts/embed_programme.py` | Embeddings `mistral-embed` |
| `frontend/src/domain/` | Modèles + ports |
| `frontend/src/application/` | Cas d’usage (`useHealth`, `useProgrammeQuery`, `useShareCard`) |
| `frontend/src/infrastructure/` | Client HTTP API, rendu canvas du visuel de partage (`renderShareCard`) |
| `frontend/src/ui/` | Composants Vue |

---

## Prérequis

- Python 3.13+
- Node.js 22.12+ (front)
- Clé API [Mistral](https://console.mistral.ai/)

---

## Lancer le projet

### 1. Backend

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
# macOS / Linux
cp .env.example .env
# Windows
copy .env.example .env
# puis renseigner MISTRAL_API_KEY dans .env
```

```bash
python scripts/scrape_programme.py
python scripts/embed_programme.py   # optionnel mais recommandé
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (dev)

```bash
cd frontend
npm install
npm run dev
```

→ [http://127.0.0.1:5173](http://127.0.0.1:5173) (proxy `/api` → `:8000`)

### 3. Frontend (prod via FastAPI)

```bash
cd frontend
npm run build
```

Puis ouvrir [http://127.0.0.1:8000](http://127.0.0.1:8000) — FastAPI sert `frontend/dist`.

---

## Fiabilité

1. **Lexical** + **sémantique** (`mistral-embed`)  
2. **Fusion RRF** des classements  
3. Le LLM ne choisit pas les sources : il ne voit que les passages déjà sélectionnés  

---

## Licence / contenu

- **Code** : MIT (à formaliser si besoin).  
- **Contenu politique** : Nouvelle Énergie / David Lisnard — citation avec lien vers la source.
