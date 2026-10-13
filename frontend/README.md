# Front Vue 3 — Programme Lisnard

UI en **clean architecture** (domain → application → infrastructure → ui).

## Lancer en dev

Prérequis : API FastAPI sur le port 8000.

```bash
# terminal 1 — racine du repo
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Ouvrir [http://127.0.0.1:5173](http://127.0.0.1:5173)  
Vite redirige `/api` → `http://127.0.0.1:8000`.

## Build production

```bash
cd frontend
npm run build
```

Génère `frontend/dist/`. FastAPI sert alors cette UI sur [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Architecture

```
src/
├── domain/            # modèles + ports (pas de Vue, pas de fetch)
├── application/       # cas d’usage (composables)
├── infrastructure/    # client HTTP de l’API, composition root
└── ui/                # composants Vue + styles
```

| Couche | Rôle |
|--------|------|
| `domain/` | `ProgrammeSource`, `CorpusHealth`, port `ProgrammeRepository`, règles de la carte partageable (`shareCard.ts`) |
| `application/` | `useHealth`, `useProgrammeQuery`, `useShareCard` (partage X) |
| `infrastructure/` | `HttpProgrammeRepository`, `apiClient`, rendu canvas du visuel 1200×675 |
| `ui/` | pages et composants purement présentationnels |
