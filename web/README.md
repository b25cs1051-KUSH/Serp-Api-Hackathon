# PharmaWatch UI

Next.js dashboard for PharmaWatch: medicine price comparison plus a live view of the SerpApi semantic cache
(every call, exact/semantic/miss, milliseconds, credits).

## Run (3 terminals, from the repo root)

```bash
docker compose up -d                                   # Redis
pip install -r requirements.txt -r api/requirements.txt
python -m uvicorn api.main:app --port 8000             # API (warms the embedding model, ~20-40 s once)
```

```bash
cd web
npm install
npm run dev                                            # http://localhost:3000
```

The API URL defaults to `http://localhost:8000`; override it with `NEXT_PUBLIC_API_URL`.
API keys stay server-side in `.env`. The browser only ever sees whether a key is configured.

## What each section shows

| Section | Source | Credits |
|---|---|---|
| Results + generics | `GET /api/search/stream` (SSE, stages arrive as they finish) | only on cache misses |
| Under the hood | `call` events: one per SerpApi request, with outcome and ms | — |
| Proof | `GET /api/stats` + `GET /api/account` (SerpApi account.json) | 0 |
| Cache lab | `GET /api/cache/lab`: nearest cached queries, cosine, dosage guard | 0 |
| What is cached | `GET /api/cache/entries`: Redis contents and TTLs | 0 |
