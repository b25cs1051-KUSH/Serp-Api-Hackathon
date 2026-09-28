# PharmaWatch

Type a medicine and your PIN code. PharmaWatch shows what it actually costs **delivered to your door**
from 13 Indian online pharmacies, and whether a **generic with the same composition** is cheaper.

```
Search: "Stamlo 5" (amlodipine 5 mg, blood pressure) · PIN 110001

  Stamlo 5 @ Chemist180     ₹66.02 delivered   ~₹2.20 / tablet (pack size estimated)
  Amlokind 5 @ Chemist180   ₹19.41 delivered   ~₹1.29 / tablet (pack size estimated)
  → same medicine, same strength: save ~41% per tablet
```

It is built on [SerpApi](https://serpapi.com) (Google Shopping + Google product pages), a Redis cache
that decides when *not* to call SerpApi, and Gemini, used for one narrow job: picking substitutes
from a curated catalogue.

---

## Contents

- [How a search works](#how-a-search-works)
- [Keeping the LLM grounded](#keeping-the-llm-grounded)
- [The cache](#the-cache)
- [Problems we hit, and what fixed them](#problems-we-hit-and-what-fixed-them)
- [What one search costs](#what-one-search-costs)
- [Setup](#setup)
- [Use it from Claude (MCP)](#use-it-from-claude-mcp)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Known limits](#known-limits)

---

## How a search works

Everything after the first step runs in parallel. Results reach the browser as each piece finishes.

```
 t=0  ┬─ Google Shopping: "Stamlo 5 price" ──▶ main list (only real Stamlo 5 listings)
      │                                         └─▶ product page links for the top 5 (parallel)
      │
      └─ Gemini + compositions.md: 3 substitutes ─┬─ search "Amlokind 5"  ─┐
                                                  ├─ search "Amtas 5"     ─┼─▶ pool every search
                                                  └─ search "Amlopres 5"  ─┘   ▶ compare per tablet,
                                                                                  delivery included
                                                                                ▶ links for the cheaper ones
```

1. **Main search.** Google Shopping via SerpApi. Listings are parsed, mapped to one of 13 known
   pharmacies, and **delivery cost for your PIN** is added: zone lookup (metro / tier 2 / tier 3 /
   remote / unserviceable), free-delivery thresholds, fee slabs and platform fees. The list is ranked
   by the delivered price, not the shelf price.
2. **Substitutes.** Gemini reads `pharmawatch/drug_db/compositions.md` (79 compositions, 307 brands)
   and returns up to 3 brands with the same active ingredient, strength and release type.
3. **Substitute searches.** All 3 run at the same moment, as soon as Gemini answers.
4. **Pooling.** Listings from all 4 searches are merged. A brand is matched against every search, not
   just its own (see [problem 3](#3-a-brands-own-search-often-doesnt-return-that-brand)).
5. **Comparison.** Per-tablet price, delivery included. Missing pack sizes are estimated and flagged.
6. **Direct links.** Resolving a listing to the pharmacy's own product page costs a SerpApi call, so it
   is done only for the top 5 main listings and for alternatives that are actually cheaper.

The browser receives four events: `main`, `main_update` (only if pooling found more listings),
`alternatives` and `main_links`, in whatever order they finish.

---

## Keeping the LLM grounded

Gemini **never sees web data**. Prices and listings from SerpApi are filtered by deterministic code;
the model only chooses from a catalogue we control, and its answer is checked before it is used.

| Step | What happens |
|---|---|
| Input | The searched name + the 79-entry catalogue (ingredient, strength, release type, brands) |
| Output | JSON with a fixed schema: `searched_brand`, up to 3 `alternatives`, a one-line `reason` |
| Validation (code) | Every alternative must be a brand **listed in the same catalogue entry** as the searched medicine. Anything else is dropped: brands from other entries, invented brands, the searched brand itself |
| Safety check (code) | A search carrying a suffix the entry doesn't list is rejected: "Telma 40 **H**" (telmisartan + hydrochlorothiazide) is not "Telma 40" |
| Cost | One call per distinct search, cached for 30 days; the cache key includes a hash of the catalogue and the prompt, so editing either invalidates old answers |
| Failure | Model chain (`gemini-2.5-flash` → `gemini-3.5-flash-lite` → …) on quota / overload / timeout; if all fail, a plain catalogue lookup takes over |

---

## The cache

`serpapi_cache/` is a drop-in replacement for `serpapi.Client.search()`:

```python
from serpapi_cache import SerpApiCache
cache = SerpApiCache()                                    # Redis on localhost:6379
result = cache.search({"engine": "google_shopping", "q": "Dolo 650 price"})
```

Each lookup goes through up to three steps:

1. **Exact match.** The normalised query (case, spacing, `500 mg` → `500mg`) is hashed and looked up.
   One Redis `GET`, no model involved.
2. **Semantic match.** The query is embedded (`all-MiniLM-L6-v2`, 384 dimensions) and compared by
   cosine similarity with everything cached. A score ≥ 0.88 is a hit.
3. **Dosage guard.** A semantic hit is refused if the numbers differ: "Metformin 500mg" never gets
   "Metformin 1000mg" results.

On top of that:

- **`exact_only=True`** skips step 2. Catalogue brand names are always searched this way (see
  [problem 1](#1-a-semantic-cache-cant-tell-two-brands-apart)).
- **Background writes.** A search that calls SerpApi returns immediately; the Redis write happens on a
  writer thread. The next search waits for any write still in flight (a few ms), so a repeat query
  always hits.
- **Call log.** Every lookup records engine, query, outcome (exact / semantic / API call), time taken,
  whether it cost a credit, and *why* it happened ("substitute search: Amlokind 5"). The UI shows it live.
- **Redis down?** The cache runs in passthrough mode: every search goes to SerpApi, nothing crashes.
- **`json_restrictor`.** PharmaWatch asks SerpApi only for the fields it reads (`pharmawatch/search.py`),
  so less is transferred and cached. The restrictor is part of the cache key, because a restricted
  response has a different shape. It is not part of the embedded text, so similarity scores are unchanged.

Measured: SerpApi calls took **1.7–12 s**; cache hits took **1–20 ms**. With `json_restrictor`, a
Google Shopping entry in Redis went from **187–282 KB to 111–125 KB** (40 results; the page tokens
needed for direct links are 58% of what is left), and a product-page entry from **~27 KB to 212 bytes**.

---

## Problems we hit, and what fixed them

Each of these came from a real run.

### 1. A semantic cache can't tell two brands apart

"Calpol 650 price" and "Dolo 650 price" are close in meaning and share the same number, so the
dosage guard lets them through. Served from cache, the user would see Dolo's prices under Calpol.

**Fix:** brand names from the catalogue are looked up by exact name only (`exact_only=True`). Their
results are still stored with an embedding, so free-text searches can reuse them.

### 2. Google Shopping returns look-alike medicines

A search for **Stamlo 5** returned 22 listings from known pharmacies. Only **8** were Stamlo 5. The
rest included **Esta 5** and **Stalopam 5** (escitalopram, an antidepressant), Stamlo **Bis**,
Stamlo **D**, Stamlo **Beta** and Met Stamlo (all combination drugs). Two of the 5 product-page
lookups, each costing a credit, went to the antidepressant.

**Fix:** a listing counts only if its title is the brand and strength. It is rejected when it carries:

- a variant suffix the brand doesn't have (SR, AT, Bis, H, Plus…);
- a second dose: "Telma AZ 40mg **8mg**", "Amlokind AT 5/**50**mg" (doses that add up to the
  brand's own, like Augmentin 625 = 500 mg + 125 mg, are fine);
- a short word between the brand and its dose: "Telma **NB** 40MG", "Telmikind **AMH** 40MG".

Checked against every cached search: the last two rules rejected exactly the 5 combination products
and **no correct listing**. The first attempt had 5 false alarms ("(Pack-30)", the site name
"| 1mg" read as a 1 mg dose, "View Uses"), which were fixed before the rules went in.

### 3. A brand's own search often doesn't return that brand

In **4 of 7** brand searches, Google Shopping returned **zero** listings of the searched brand from
the pharmacies we cover. Dolo 650, Amlopres 5, Amtas 5 and Glyciphage SR 500 came back as other
strengths or other brands.
Yet Amlopres 5 listings *did* appear in the Stamlo 5 and Amtas 5 searches.

**Fix:** every brand is matched against the pooled listings of all searches in the run. That found
Amlopres 5 at Kogland (₹3.87 / tablet) at no extra cost.

### 4. Titles often don't say how many tablets

"Stamlo 5MG Tablet ₹66.02". Is that 15 tablets or 30? Without a pack size there is no per-tablet
price, and the cheapest offer in that run (Chemist180, free delivery) was being skipped.

**Fix:** estimate the pack size from the same brand's other listings, choosing the size that gives a
consistent per-tablet price. For Telma 40, 1mg's ₹99.80 is a **15**-strip (₹6.65 / tablet, close to
the brand's ₹6.43 median), not a 30, even though 30 is the more common size. Dawaa Dost's product
URL for its ₹91 Telma 40 (`…telma-40mg-tablet-15s`) confirms that this price range is a 15-strip.
Every estimate is flagged (`pack_estimated`,
`estimated`) and shown with a "~" in the UI. Implausible estimates (outside 0.5–2× the median) are
not used.

### 5. Shelf price is not what you pay

Apollo's Stamlo-5 15's costs ₹40 on the shelf and **₹120** delivered to 110001. Chemist180 charges
₹66.02 with free delivery. Ranking by delivered price reverses the order.

### 6. Step by step was slow

The 9 SerpApi calls of the Telma 40 run add up to **33.8 s** if made one after another. In parallel,
main results arrived at **2.6 s**, generic alternatives at **5.2 s**, and all product links at
**8.1 s**. Alternatives don't wait for the main product links, which are the slowest step.

### 7. The embedding model took 40–100 s to load

Timing each import showed two causes:

- **~20 s: a Windows library clash.** torch and scikit-learn each ship their own OpenMP runtime.
  Loading scikit-learn's *after* torch's (the order `sentence-transformers` uses) took ~20 s, while
  the reverse order takes ~1.5 s. The cache now imports scikit-learn first.
- **~7 s: update checks.** The model was re-checked against HuggingFace on every start. It now loads
  from the local copy and goes online only if it isn't downloaded.

Start-up went from 41–98 s to **~10 s**. The API warms up on a background thread at start.

### 8. A cache write could be lost at shutdown

With writes on a background thread, a process exiting right after a search lost its write: the
writer loaded the embedding model while Python was shutting down, and that import failed. The model
is now loaded on the calling thread before the write is handed off. Verified across two processes:
the second one gets a cache hit with 0 API calls.

### 9. An emoji made every search cost a credit

With the API running in the background on Windows, output goes to a log whose encoding can't show
emoji. The "✅ Redis connected" message then raised an error *inside* the Redis connection code, the
cache read that as "Redis unreachable", and it silently switched to passthrough: every search
went to SerpApi, while Redis was up the whole time.

**Fix:** every message from the cache library goes through a print helper that replaces characters
the console can't show instead of raising. Verified with a cp1252 console: the cache stays on Redis.

---

## What one search costs

| Call | SerpApi credits | When |
|---|---|---|
| Main search | 1 | Always, unless cached (24 h) |
| Substitute searches | up to 3 | Unless cached |
| Product-page links, main list | up to 5 | Only the top 5 real matches |
| Product-page links, alternatives | 0–3 | Only alternatives that are cheaper |
| Gemini | 0 SerpApi credits | Once per distinct search, then cached |

A new medicine costs at most 12 credits (9 in each of our live runs). Repeating it within 24 hours
costs **0**, and a later search
for one of its substitutes reuses that substitute's cached listings.

---

## Setup

Requirements: Python 3.10+, Docker (for Redis), Node 20+ (for the web UI).

```bash
# 1. Redis (data persists in a Docker volume)
docker compose up -d

# 2. Python dependencies
pip install -r requirements.txt -r api/requirements.txt

# 3. Keys: .env in the repo root (git-ignored)
SERP_API_KEY=...
GEMINI_API_KEY=...
# optional: GEMINI_MODEL=gemini-2.5-flash,gemini-2.5-flash-lite
# optional: MAX_CONCURRENT_SEARCHES=4  SEARCH_TIMEOUT_S=90  SERPAPI_TIMEOUT=30
# optional: UI_ORIGINS=http://localhost:3000   (CORS)

# 4. API
uvicorn api.main:app --port 8000

# 5. Web UI (http://localhost:3000)
cd web && npm install && npm run dev
```

### API endpoints

| Endpoint | What it returns |
|---|---|
| `GET /api/search/stream?q=Stamlo 5&pincode=110001` | Server-Sent Events: `main`, `main_update`, `alternatives`, `main_links`, plus every SerpApi call live and a summary |
| `GET /api/search?q=Stamlo 5&pincode=110001` | The same search as one JSON response. 422 bad input, 429 busy, 504 deadline passed, 502 pipeline error (the last two still include partial results) |
| `GET /api/health` | Redis status, model warm-up state, whether keys are configured (never the keys) |
| `GET /api/account` | SerpApi plan usage (free call, cached 30 s) |
| `GET /api/stats` | Cache hit rate, credits spent and saved in this process |
| `GET /api/cache/lab?q=...` | What the cache *would* do with a query: nearest cached queries, similarity, dosage guard. Read-only, 0 credits |
| `GET /api/cache/entries` | Everything in Redis, with time left |

### Guards

A search can spend up to 12 credits, so the API protects them:

- **Input is checked before anything runs.** A bad PIN or an empty query is refused and costs nothing.
- **At most `MAX_CONCURRENT_SEARCHES` (default 4) run at once.** More are refused with a clear message.
  A search keeps its slot until its pipeline finishes, even if the browser disconnects.
- **`SEARCH_TIMEOUT_S` (default 90)** caps how long a request waits; anything fetched so far is still
  returned and cached.
- **`SERPAPI_TIMEOUT` (default 30 s)** on every SerpApi request. The client's default is no timeout.
- **The live call log is trimmed** as soon as no running search can still need an entry, so a
  long-running server doesn't grow.

On the stream endpoint a refused search still answers `200` with an `error` event (`code`:
`invalid_query`, `invalid_pincode`, `busy`, `timeout`, `pipeline_error`) followed by `done`, because a
browser `EventSource` can't read an HTTP error body.

### Keys and secrets

- Keys live only in `.env`, which is git-ignored.
- The Gemini key is sent in a request header, not the URL.
- API responses report *whether* a key is configured, never its value.
- Errors from the SerpApi account lookup are reported without the request URL, which contains the key.

---

## Use it from Claude (MCP)

`mcp_server.py` exposes PharmaWatch as an [MCP](https://modelcontextprotocol.io) server over stdio,
built on the official Python SDK. Each tool is a thin wrapper over `api/main.py`, so input validation,
the concurrency limit, the search deadline and credit accounting are the same as the HTTP API.

| Tool | What it does | Credits |
|---|---|---|
| `search_medicine(query, pincode, resolve_links=false)` | Delivered-price ranking for the PIN, cheaper generics with per-tablet savings, and a calls/credits summary | up to ~12 for a new medicine, 0 from cache |
| `cache_lab(query, top=6)` | What the cache would do: exact key, nearest cached queries with cosine scores, the dosage guard | 0 |
| `cache_stats()` | Redis status, what is cached (by kind and size), credits spent vs saved this session | 0 |

Design choices:

- **Markdown by default, JSON on request.** Tools return a compact Markdown answer for the model's
  context (top 10 listings, no thumbnails or page tokens). `response_format="json"` returns the same
  data as trimmed JSON.
- **Credit-safe defaults.** `resolve_links` is off unless the user asks for direct pharmacy URLs. The
  server instructions tell the model to call `cache_lab` first when credits matter.
- **Tool annotations.** `cache_lab` and `cache_stats` are marked read-only. `search_medicine` is marked
  open-world, non-destructive and idempotent (a repeat is served from cache).
- **Errors the model can act on.** A bad PIN or query comes back as a tool error
  (`invalid_pincode: ...`) before anything is spent. A search that fails halfway still returns what it
  found, marked "Search incomplete".
- **Progress.** `search_medicine` reports each SerpApi lookup and each finished stage as MCP progress
  notifications.
- **Clean stdout.** The protocol runs on a private copy of stdout. Console prints from the cache and
  library warnings go to stderr, which MCP clients keep as the server log.

**Claude Desktop** (`claude_desktop_config.json`; use your own absolute path and Python):

```json
{
  "mcpServers": {
    "pharmawatch": {
      "command": "python",
      "args": ["/absolute/path/to/Serp-Api-Hackathon/mcp_server.py"]
    }
  }
}
```

The server reads `.env` from the repo root, whatever directory the client starts it in. Redis must be
running (`docker compose up -d`).

**MCP Inspector:**

```bash
npx @modelcontextprotocol/inspector python mcp_server.py                     # web UI
npx @modelcontextprotocol/inspector --cli python mcp_server.py --method tools/list
```

**Example.** Asking Claude *"Where is Stamlo 5 cheapest delivered to 110001, and is there a cheaper
generic?"* makes it call `search_medicine`. Real output from a cached run (links shortened):

```markdown
## Stamlo 5: delivered prices to PIN 110001

Cheapest delivered: **₹66.02** at Chemist180 (FREE delivery on every order).

| # | Pharmacy | Product | Shelf price | Delivery | You pay | Arrives | Link |
|---|---|---|---|---|---|---|---|
| 1 | Chemist180 | Stamlo 5MG Tablet | ₹66.02 | FREE delivery on every order | ₹66.02 | 2-4 Days | [open](…) |
| 2 | Medplus | Stamlo 5MG Tab | ₹80.51 | FREE delivery on every order | ₹80.51 | Same Day / Store Pickup | [open](…) |
| 3 | Apollo Pharmacy | Stamlo-5 Tablet 15's | ₹40.00 | ₹80 delivery · add ₹159 more for FREE delivery | ₹120.00 | 10-30 Mins / 1 Day | [open](…) |
| 4 | 1mg | Stamlo 5 Tablet | ₹76.60 | ₹50 delivery · add ₹23.40 more for FREE delivery | ₹126.60 | 1-2 Days | [open](…) |
| 5 | Apollo Pharmacy | Stamlo-5 Tablet 30's | ₹80.00 | ₹80 delivery · add ₹119 more for FREE delivery | ₹160.00 | 10-30 Mins / 1 Day | [open](…) |
| 6 | PharmEasy | Stamlo 5Mg Strip Of 30 Tablets | ₹61.99 | ₹120 delivery · add ₹338.01 more for FREE delivery | ₹181.99 | 1-2 Days | [open](…) |

### Generic alternatives: Amlodipine Besylate 5mg (Immediate Release)
Reference: Stamlo 5MG Tablet at ₹66.02, ₹2.20/tablet.

| Brand | Pharmacy | You pay | Per tablet | Pack | Saving |
|---|---|---|---|---|---|
| Amlokind 5 | Chemist180 | ₹19.41 | ₹1.29 | ~15 (est.) | ≈41.4% (₹0.91/tablet) |

~ = pack size estimated, ≈ = saving depends on it.

### Run
4 SerpApi lookups · 0 credits spent · 4 served from cache (4 exact, 0 semantic) · 0.1 s
```

---

## Tests

```bash
python scripts/test_p5_generics.py                           # 101 offline checks, 0 credits
python scripts/test_p4_delivery_cost.py                      # delivery rules, 0 credits
python scripts/test_api.py                                   # 38 API checks, stubbed pipeline, 0 credits
python scripts/test_mcp.py                                   # MCP tools in memory + 3 real stdio sessions, 0 credits
python scripts/test_p5_generics.py --llm "dollo 650" "Telma 40 H"          # Gemini only, 0 SerpApi credits
python scripts/test_p5_generics.py "Stamlo 5" 110001 --cache-only          # replay from Redis, 0 credits
python scripts/test_p5_generics.py "Stamlo 5" 110001                       # live run, full call log
```

The offline checks use real titles and prices from live runs, and cover the matching rules, pack
estimation, catalogue validation, exact-only caching, background writes, the parallel timing, and a
full pipeline replay with stubbed searches (including a misspelled search, a medicine outside the
catalogue, and a failing substitute search).

`--cache-only` serves everything from Redis and blocks any call that would cost a credit, listing
what a live run would still pay for.

---

## Project layout

```
serpapi_cache/          cache library: exact → semantic → dosage guard, Redis backend,
                        background writes, call log
pharmawatch/
  search.py             SerpApi queries (Google Shopping, product pages)
  distiller.py          SerpApi JSON → clean listings, pharmacy detection
  delivery_cost.py      PIN zone + per-pharmacy delivery rules → delivered price
  comparator.py         ranking by delivered price
  generics.py           catalogue matching, brand/strength filtering, pooling, pack estimation
  gemini.py             Gemini REST client (JSON schema, model fallback chain)
  pipeline.py           the parallel search, streamed as events
  drug_db/compositions.md   79 compositions, 307 brands
notes/postal_codes_delivery_rules.json   PIN zones and delivery fees per pharmacy
api/                    FastAPI layer (SSE search, health, cache lab)
mcp_server.py           MCP server (stdio): the same search and cache lab as tools
web/                    Next.js UI
scripts/                offline tests, live replay, threshold tuning
docker-compose.yml      Redis with append-only persistence
```

---

## Known limits

- **Google Shopping coverage.** Some brands are not listed at all (Amtas 5, Telvas 40); pooling helps
  but cannot invent listings.
- **Estimated pack sizes are estimates.** They are always flagged; a pharmacy selling an unusual pack
  can still be misread.
- **Catalogue size.** Substitutes come only from `compositions.md` (79 compositions). A medicine outside
  it still gets prices, but no alternatives.
- **Strict matching.** "Augmentin 625 Duo" is rejected because "Duo" is treated as a different product;
  adding the variant to the catalogue fixes it.
- **Delivery fees** come from each pharmacy's published rules and can change.

---

## License

MIT
