# PharmaWatch UI

Next.js app for PharmaWatch: Indian medicine prices delivered to your PIN, cheaper same-salt brands, the
cheapest way to buy a whole prescription, and a live view of the SerpApi semantic cache behind it.

## Run (3 terminals, from the repo root)

```bash
docker compose up -d redis                             # Redis
pip install -r requirements.txt -r api/requirements.txt
python -m uvicorn api.main:app --port 8000             # API (warms the embedding model, ~20-40 s once)
```

```bash
cd web
npm install
npm run dev                                            # http://localhost:3000
```

The API URL defaults to `http://localhost:8000`; override it with `NEXT_PUBLIC_API_URL` (read at build time).
API keys stay server-side in `.env`. The browser only ever sees whether a key is configured.

## Routes

Every page is client-rendered and static (`npm run build` lists `/`, `/shop`, `/engine` as static), so the
site also works as a static export.

| Route | What it is |
|---|---|
| `/` | Landing page: what PharmaWatch does, a real recorded prescription run (`src/data/demo-prescription.json`) beside its SerpApi calls, "Run it live", capabilities with measured numbers, how it works, the benchmark, MCP / API / docker for developers. Renders fully while the API sleeps. |
| `/shop` | The store, light and non-technical. Tabs: **One medicine** (search, best delivered offer, other pharmacies, filters, same-salt swaps) and **Whole prescription** (paste or type medicines, common prescriptions, then three plans, each with its orders, Buy links, open-all and copy shopping list). `/shop?tab=rx` opens the prescription tab. |
| `/engine` | Under the hood: the same searches with every SerpApi call live (exact / semantic / API, ms, credits), "run again: 0 credits", the direct-links toggle, status pills, how the cache decides, Cache Lab, the Redis explorer, session stats and the SerpApi quota. |
| `/?view=engine` | Old link; redirects to `/engine`. |

Deep links into `/engine` start a run with direct pharmacy links off (so opening a link never pays for
product pages):

- `/engine?q=Dolo%20650&pin=110001`: one medicine
- `/engine?rx=Dolo%20650%20x15;Stamlo%205&pin=110001`: a prescription, one medicine per `;` or new line

## Where the data comes from

| Section | Source | Credits |
|---|---|---|
| Prices, generics | `GET /api/search/stream` (SSE, stages arrive as they finish) | only on cache misses |
| Prescription | `GET /api/prescription/stream` (SSE: each line, then the basket) | only on cache misses |
| Product page on click | `GET /api/link/{id}` (redirects to the pharmacy's page for that listing) | 1 the first time, then cached |
| Call log (`/engine`) | `call` events: one per SerpApi request, with outcome and ms | — |
| Stats, quota | `GET /api/stats` + `GET /api/account` (SerpApi account.json) | 0 |
| Cache Lab | `GET /api/cache/lab`: nearest cached queries, cosine, dosage guard | 0 |
| What is cached | `GET /api/cache/entries`: Redis contents and TTLs | 0 |

Every EventSource is closed on `done` or `error` and never reconnects: a reconnect would re-run the search
and spend credits.

## Code layout

- `src/app/`: `page.tsx` (landing), `shop/page.tsx`, `engine/page.tsx`, `layout.tsx` (fonts, titles), `globals.css` (tokens; `.theme-light` and `.theme-console` scopes)
- `src/components/views/`: `ShopView`, `EngineView`
- `src/components/landing/`: landing sections, `content.ts` (every number with its source), `DemoPanel`
- `src/components/shop/`: shop header, product card, swap section, receipt, states and filters
- `src/components/shell/`: site header and footer, search box, status pills, the `/?view=engine` redirect
- `src/components/`: shared result components used by both shop and engine (basket, plans, orders, comparison, call log, cache views)
- `src/lib/`: `api.ts` (types, `buyLink`), `useSearch`, `usePrescription`, `useApiStatus`, `kits.ts` (common prescriptions)
