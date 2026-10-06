# PharmaWatch

Type a medicine, or a whole prescription, and your PIN code. PharmaWatch shows what it actually costs
**delivered to your door** from 13 Indian online pharmacies, finds **brands with the same composition**
that are cheaper, and works out the **cheapest way to buy everything**, delivery fees included.

```
Prescription · PIN 110001: Dolo 650 ×30 tablets, Stamlo 5, Atorbest 10

  Cheapest basket  ₹93.37   one order at Chemist180, free delivery
    Paracip 650  3 × 10   ₹41.82   ₹1.39/tablet   same salt as Dolo 650    (₹1.75/tablet)
    Amodep 5     2 × 15   ₹30.16   ₹1.01/tablet   same salt as Stamlo 5    (₹2.20/tablet)
    Torvason 10  1 × 10   ₹21.39   ₹2.14/tablet   same salt as Atorbest 10 (₹3.66/tablet)
  → ₹61.85 less than the prescribed brands (₹155.22), 40% of the bill
```

It is built on [SerpApi](https://serpapi.com) (Google Shopping + Google product pages), a Redis cache
that decides when *not* to call SerpApi, an index of 246,046 Indian medicines that says which brands
share a composition, and Gemini, used for one narrow job: reading misspellings.

---

## Contents

- [How a search works](#how-a-search-works)
- [A whole prescription](#a-whole-prescription)
- [Cheaper than the pharmacies' own suggestions](#cheaper-than-the-pharmacies-own-suggestions)
- [Medicine data](#medicine-data)
- [Keeping the LLM grounded](#keeping-the-llm-grounded)
- [The cache](#the-cache)
- [Problems we hit, and what fixed them](#problems-we-hit-and-what-fixed-them)
- [What one search costs](#what-one-search-costs)
- [Setup](#setup)
- [Use it from Claude or Codex (MCP)](#use-it-from-claude-or-codex-mcp)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Known limits](#known-limits)

---

## How a search works

Everything after the first step runs in parallel. Results reach the browser as each piece finishes.

```
 t=0  what is "Stamlo 5"?  medicine index, ~1 ms, 0 credits → Amlodipine 5mg tablet, 281 brands
      │   ("paracetamol" without a strength → the user picks one first; nothing is searched)
      │
      └─ Google Shopping: "Stamlo 5 price" ──▶ main list (only real Stamlo 5 listings)
            │                                 └─▶ product page links for the top 5 (parallel)
            │
            ├─ "Amlodipine 5mg tablet generic" ─┐  pool all 3 searches
            └─ "Amlopres 5" (Cipla)            ─┴▶ every brand of the salt found anywhere,
                                                    per tablet, delivery included
                                                  ▶ links for the cheaper ones
```

1. **What the search names.** `pharmawatch/medicines.py` looks the words up in an index of **246,046
   Indian medicines** (see [Medicine data](#medicine-data)): a brand ("Stamlo 5"), a salt
   ("Gliclazide 80mg") or a name that needs a strength first ("paracetamol", "Dolo"). Spelling is
   corrected against the index ("dollo 650" → Dolo 650).
2. **Main search.** Google Shopping via SerpApi. Listings are parsed, mapped to one of 13 known
   pharmacies, and **delivery cost for your PIN** is added: zone lookup (metro / tier 2 / tier 3 /
   remote / unserviceable), free-delivery thresholds, fee slabs and platform fees. The list is ranked
   by the delivered price, not the shelf price. For a salt search the main list is every brand of
   that exact composition.
3. **Substitute searches.** Every brand with the same composition key (salts, strengths, form,
   release type) is a substitute. Two searches are added, chosen for reach: the salt + "tablet
   generic" (Google then lists the discounted generics pharmacies push) and the Cipla brand of the
   salt with the largest family (a salt search without one gets the brand whose maker has the widest
   range). See [problem 11](#11-picking-brands-to-search-by-list-price-was-a-guess) and
   [problem 12](#12-the-pharmacies-favourite-generics-are-cheap-only-after-discount).
4. **Pooling.** Every listing from all 3 searches is checked against **every** brand of the
   composition, so brands nobody searched for are compared too (see
   [problem 3](#3-a-brands-own-search-often-doesnt-return-that-brand)).
5. **Comparison.** Per-tablet price, delivery included. Missing pack sizes are estimated from the
   brand's other listings, then from its usual pack in the index, and flagged.
6. **Direct links.** Resolving a listing to the pharmacy's own product page costs a SerpApi call, so it
   is done only for the top 5 main listings and for alternatives that are actually cheaper.

The browser receives four events: `main`, `main_update` (only if pooling found more listings),
`alternatives` and `main_links`, in whatever order they finish, or a single `choose` event when the
search needs a strength first.

---

## A whole prescription

Up to 8 medicines, each with an optional number of tablets (else one pack of the prescribed
medicine). Every line is resolved in the medicine index at once, a line without a strength
("paracetamol") asks for one and the rest carry on, and **every search of every line runs at the
same time**: 3 medicines take about as long as 1.

Then the basket is optimised as a whole (`pharmawatch/basket.py`). Each pharmacy charges delivery on
its own order total (1mg free from ₹100, Apollo from ₹199, Netmeds from ₹500, Chemist180 always), so
buying each medicine where it is cheapest alone can cost more than putting two in one order.

- Every same-composition offer covers the needed tablets in whole packs.
- Assignments of medicines to pharmacies are priced with the real delivery rules on each pharmacy's
  subtotal, by branch and bound: delivery fees are never negative, so item costs so far plus the
  cheapest possible remaining items bound any basket, and branches that can't win are cut. It is exact
  over the cheapest offer per pharmacy and medicine, checked against brute force on 200 random
  baskets. 8 medicines × 7 pharmacies (5.7 million assignments): about 2 ms.
- Two answers: **cheapest with same-salt swaps** and **exactly as prescribed**, plus the best single
  pharmacy and the saving (compared on the medicines both can cover).
- Direct product links are resolved only for the offers the basket picked.

The UI's *Whole prescription* tab streams each medicine as it finishes; *Under the hood* shows every
lookup of every line and how many assignments the optimiser priced. The same basket is available as
`GET /api/prescription/stream`, `GET /api/prescription` and the MCP tool `plan_prescription`.

## Cheaper than the pharmacies' own suggestions

1mg, Chemist180 and Medplus show a "cheaper alternative" on a medicine's page. PharmaWatch has to
beat it, or the product makes no sense. `scripts/reference_check.py` checks this on 15 common
medicines and 4 prescriptions: it reads Chemist180's own suggestion from its product page (as a test
reference only; the product itself uses SerpApi alone) and compares it with our cheapest
same-composition offer, per tablet, delivered. Latest run (`scripts/reference_report.md`):

**10 of 15 at or below the pharmacy's cheapest; all 4 prescription baskets pass.**

| Medicine | Chemist180's suggestion | PharmaWatch's cheapest |
|---|---|---|
| Thyronorm 50 | Thiroace 50, ₹0.70 | **Thyrorich 50 @ Chemist180, ₹0.14** |
| Pan 40 | Prasopheg 40, ₹2.25 | **Pantopraz 40 @ Chemist180, ₹0.66** |
| Stamlo 5 | Amlip 5, ₹1.35 | **Amodep 5 @ Chemist180, ₹1.01** |
| Atorbest 10 | Lipvas 10, ₹3.30 | **Atorless 10 @ Chemist180, ₹2.73** |
| Azithral 500 | Azikem 500, ₹18.12 | **Azivent 500 @ Chemist180, ₹14.78** |
| Dolo 650 | Paracip 650, ₹1.39 | Paracip 650 @ Chemist180, ₹1.39 |
| Rosuvas 10 | Rosemicor 10, ₹2.25 | Rosudac 10, ₹2.94 (miss) |
| Montair LC, Glycomet GP 2, Pantocid DSR, Amlokind AT | Chemist180's combination generics | miss: Google Shopping didn't list them for any query we tried |

How: besides the main search, each medicine gets up to three searches chosen for reach (see
[problem 12](#12-the-pharmacies-favourite-generics-are-cheap-only-after-discount) and
[problem 15](#15-a-pharmacys-own-generics-show-up-only-when-you-name-the-pharmacy)).

## Medicine data

Substitutes come from the **Indian Medicine Dataset** (253,973 medicines, MIT licence,
[junioralive/Indian-Medicine-Dataset](https://github.com/junioralive/Indian-Medicine-Dataset)).
`scripts/build_medicine_index.py` turns it into `pharmawatch/drug_db/medicines.sqlite.gz` (7 MB):
246,046 products that aren't discontinued, 17,028 compositions and 7,641 manufacturers.

Each product gets a **composition key**: its salts with strengths, its form and its release type.
Products with the same key are interchangeable brands; anything else is a different medicine.

| Search | Key | Brands | Not in the group |
|---|---|---|---|
| Gliclazide 80mg | `gliclazide:80mg\|tablet\|` | 116 (Glizid 80, Diamicron 80, Glycigon ...) | Glizid-M, Reclimet (+ metformin) |
| Sitagliptin 50mg | `sitagliptin:50mg\|tablet\|` | 54 (Januvia 50, Istavel 50, Sitacip 50 ...) | Istamet (+ metformin), Setalin 50 (sertraline) |
| Glyciphage SR 500 | `metformin:500mg\|tablet\|sr` | SR brands only | Glyciphage 500 (immediate release) |

The list prices (MRP) in the dataset only decide which brands are worth searching. Every price shown
comes live from SerpApi.

## Keeping the LLM grounded

Gemini **never sees web data** and never names a medicine on its own. It has one job: when a
misspelt search could be several medicines, pick which one the user meant **from candidates the
index returns**.

| Step | What happens |
|---|---|
| Input | The search + up to 4 index candidates, each with its composition |
| Output | JSON with a fixed schema: the `choice` (a candidate number or null) and a one-line `reason` |
| Validation (code) | The choice must be one of the candidates; anything else is ignored |
| Cost | Only for ambiguous spellings. Cached for 30 days; the key includes a hash of the index and the prompt |
| Failure | Model chain (`gemini-2.5-flash` → `gemini-3.5-flash-lite` → …) on quota / overload / timeout; if all fail, the closest spelling is used |

Everything else (brand vs salt, which brands are substitutes, which listing is which brand) is
deterministic code over the index.

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

- **Same params only.** A semantic hit is only served from an entry fetched with the same other params
  (page, filters, language, `json_restrictor`), checked by a stored hash of those params. The embedding
  only sees the query text, so without this "Dolo 650, page 2" could get page 1's results.
- **Thin results expire in 1 h.** Google sometimes answers "Stamlo 5 price" with other brands only. A
  main search that finds fewer than 3 real listings of the medicine is cached for 1 h instead of 24 h
  (`ttl_for` in `SerpApiCache.search`), so a bad response doesn't stick for a day.
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

**Fix:** substitute brand names are looked up by exact name only (`exact_only=True`). Their
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

### 10. A hand-written catalogue was wrong, and too small

The first version took substitutes from `compositions.md`: 79 entries written with an LLM's help.
Salt searches such as "Gliclazide 80mg" and "Sitagliptin 50mg" showed **0 listings**, because Google
returns brand names and the filter looked for the salt in the title. Checking the catalogue against
a real dataset also showed errors: **Istamet 50** (sitagliptin + metformin) and **Reclimet**
(gliclazide + metformin) were listed as plain single-salt brands, and **Zita 50** is not sitagliptin
at all. A title Google returned for "Sitagliptin 50mg", **Setalin 50**, turned out to be sertraline,
an antidepressant.

**Fix:** the catalogue was replaced by the 246,046-medicine index. A salt search now matches any
brand with exactly that composition (Gliclazide 80mg: 18 listings from real cached results, where it
showed 0), combinations are separate keys, and a listing only counts when its title is a brand the
index places in the same group.

### 11. Picking brands to search by list price was a guess

The first version of the index-based search picked 3 cheap brands of the same salt by list price
and searched each by name. Live, for Gliclazide 80mg, none of the 3 (Glypen 80, Glurib 80, Glic 80)
appeared in its own results. Their results still held other gliclazide brands, which pooling picked
up (20 of the 25 listings), so any search in the same salt widens the pool.

**Fix:** one extra search, chosen for reach. A brand search adds the salt ("Stamlo 5" → "Amlodipine
5mg": 9 same-salt brands, 3 of them 28–48% cheaper per tablet). A salt search adds the brand whose
maker has the widest range ("Sitagliptin 50mg" → Istavel 50: 2 listings became 14). A new medicine
costs 2 credits instead of 4.

### 12. The pharmacies' favourite generics are cheap only after discount

On 1mg, Chemist180 and Medplus, the "cheaper alternative" for Dolo 650, Stamlo 5 and Atorbest 10 was a
Cipla brand every time (Paracip 650, Parafast 650, Amlip 5, Lipvas 10). By list price they are
**expensive**: Paracip ranks 449th of 500 paracetamol-650 brands, Amlip 243rd of 281, Lipvas 557th of
655. They are cheap only after the pharmacies' discount (Amlip: ₹3.24 list, ₹1.35 sold), so no
list-price rule finds them, and Google's plain salt search didn't return them either.

**Fix:** two searches chosen for reach. One is the salt + "tablet generic", which steers Google to
discounted generics ("Atorvastatin 10mg tablet generic" found Torvason 10 at ₹2.14/tablet; the plain
salt found ₹2.47). The other is the Cipla brand with the largest family ("Paracip 650", not the thin
"Cipmol 650": 29 listings of 10 same-salt brands). Every result is pooled and checked against the
whole composition group.

### 13. The semantic cache served one brand's results for another

"Atorbest 10 price" was answered from the cached search of another atorvastatin brand: same dose,
similar text, similarity above 0.88. The main list came back empty.

**Fix:** a search the index identifies as a brand is looked up by exact name only, like substitute
searches (problem 1). Salt searches still use the semantic cache.

### 14. Google answered some brands with other brands only

"Pan 40 price" returned 24 listings of other pantoprazole brands and not one Pan 40; "Atorbest 10
price" returned Atorbest 20 only. The prescribed brand then looked unavailable, and the basket could
not compare it.

**Fix:** when a brand's own search has none of it, one more search adds the form word ("Pan 40
tablet": 5 listings of Pan 40; "Atorbest 10 tablet": 6). In a 5-medicine prescription this turned
"compared on 3 of 5 medicines" into all 5: ₹560.00 as prescribed vs ₹415.16 cheapest.

### 15. A pharmacy's own generics show up only when you name the pharmacy

Chemist180's suggested alternatives for Pan 40, Thyronorm 50 and Rosuvas 10 were its own discounted
generics (Prasopheg 40, Thiroace 50, Rosemicor 10), and none appeared in any of our searches; their
makers have nothing in common, so no rule over the index predicts them. Google Shopping does list
them, only for the right words: "Pantoprazole 40mg tablet generic chemist180" returned Pantopraz 40 at
₹0.66/tablet, a third of the pharmacy's own suggestion.

**Fix:** single-salt medicines get that search too. Measured on 15 medicines, it raised the
reference check from 6 to 10 passes. Combinations stay a gap: the same wording returned nothing for
them, and naming the brand ("Amlokind AT chemist180") finds only the brand itself.

## What one search costs

| Call | SerpApi credits | When |
|---|---|---|
| Main search | 1 | Always, unless cached (24 h) |
| Generic salt search | 1 | "Amlodipine 5mg tablet generic" for Stamlo 5 |
| Chemist180 generic search | 0–1 | "Amlodipine 5mg tablet generic chemist180"; single-salt medicines only |
| Brand retry | 0–1 | Only when Google's answer to a brand has none of it ("Pan 40" → "Pan 40 tablet") |
| Discounted-generic brand | 1 | The Cipla brand of the salt with the largest family ("Paracip 650"); for a salt search without one, the brand with the widest maker range |
| Product-page links, main list | up to 5 | Only the top 5 real matches, only when links are on |
| Product-page links, alternatives | 0–3 | The 3 cheapest alternatives that beat the searched brand |
| Gemini | 0 SerpApi credits | Only for misspellings with several possible readings, then cached |
| A search without a strength ("paracetamol") | 0 | The user picks a strength first |

A new medicine costs at most 12 credits, and **4** with links off (3 for a combination). Repeating it within 24 hours
costs **0**, and a later search that shares a salt reuses the cached searches. A prescription costs
the sum of its new medicines, with links resolved only for the offers the basket picked.

---

## Setup

### Quickstart with Docker (one command)

Requirements: Docker. Put your keys in `.env` in the repo root (git-ignored):

```bash
SERP_API_KEY=...
SERP_API_KEY_2=...
GEMINI_API_KEY=...
```

The second SerpApi key is optional. Docker Compose uses it only after the first key runs out.

Then:

```bash
docker compose up --build
```

Open http://localhost:3000. The API is on http://localhost:8000.

- Three containers: Redis (append-only file, data kept in a volume), the API and the UI. Each has a
  healthcheck, and the UI starts once the API is healthy.
- The embedding model is downloaded during the build, so the first search doesn't wait for it.
- Keys are read from `.env` when the containers start and are never copied into an image
  (`.dockerignore` excludes `.env`). Both app containers run as non-root users.
- The first build downloads about 1 GB (CPU-only PyTorch) and takes a few minutes. The API image is
  about 2.2 GB and the UI image about 330 MB.

### Local development

Requirements: Python 3.10+, Docker (for Redis), Node 20+ (for the web UI).

```bash
# 1. Redis only (data persists in a Docker volume)
docker compose up -d redis

# 2. Python dependencies
pip install -r requirements.txt

# 3. Keys: .env in the repo root (git-ignored)
SERP_API_KEY=...
GEMINI_API_KEY=...
# optional: GEMINI_MODEL=gemini-2.5-flash,gemini-2.5-flash-lite
# optional: MAX_CONCURRENT_SEARCHES=4  SEARCH_TIMEOUT_S=90  SERPAPI_TIMEOUT=30
# optional: UI_ORIGINS=http://localhost:3000   (CORS)
# optional: REDIS_HOST=localhost  REDIS_PORT=6379

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

## Use it from Claude or Codex (MCP)

PharmaWatch is an [MCP](https://modelcontextprotocol.io) server, built on the official Python SDK, in two ways:

- **Public connector, nothing to install:** `https://pharmawatch-api-zmwy.onrender.com/mcp` (Streamable HTTP),
  served by the same process as the website's API. `server.json` describes it for the official MCP Registry as
  `io.github.b25cs1051-KUSH/pharmawatch`.
- **Local, over stdio:** `python mcp_server.py`, for Claude Desktop, Cursor and MCP Inspector with your own keys.

Every tool calls the same code as the web app's HTTP API (`api/main.py`), so input validation, the concurrency
limit, the search deadline, the daily credit budget and credit accounting are shared. An agent gets the same
answers a shopper gets on the website.

| Tool | What it does | Credits |
|---|---|---|
| `search_medicine(query, pincode, resolve_links=false)` | Listings ranked by what the buyer pays delivered to the PIN, cheaper same-salt brands with per-tablet savings, spelling correction, a strength prompt for names like "paracetamol" | ~4 for a new medicine, 0 from cache |
| `plan_prescription(medicines[{name, tablets?}], pincode, resolve_links=false)` | The cheapest way to buy a whole prescription: three plans (cheapest with swaps, one pharmacy, exactly as prescribed) as orders per pharmacy with delivery, the swap saving, a per-medicine comparison, and lines that need a strength | ~4 per new medicine, 0 from cache |
| `get_buy_link(listing_id)` | The listing's own pharmacy product page, resolved on demand: the same lookup as a Buy click in the web app (`/api/link/{id}`) | 1 the first time, then 0 for 24 h |
| `cache_lab(query, top=6)` | What the cache would do: exact key, nearest cached queries with cosine scores, the dosage guard | 0 |
| `cache_stats()` | Redis status, what is cached (by kind and size), credits spent vs saved in this server | 0 |

Prompts: `compare_medicine(medicine, pincode)` and `plan_my_prescription(prescription, pincode)`, which clients show
as ready-made actions.

Design choices:

- **Typed output and readable text.** Every tool publishes an `outputSchema` and returns `structuredContent`
  (all listings, ids, link types, savings, run summary) alongside a compact Markdown answer for the model's
  context. `response_format="json"` returns the structured data as the text too.
- **Links an agent can act on.** Every listing and basket item has a `listing_id` and a `link_type`
  (`product_page`, `store_search`, `google_shopping`). The agent calls `get_buy_link` only for the offer the user
  picks, instead of resolving every link up front. Only that pharmacy's page is returned, never another store's.
- **Schemas every client can read.** `$ref`/`$defs` are inlined, so clients that don't resolve references still
  see that a prescription item has `name` and `tablets`.
- **Credit-safe defaults.** `resolve_links` is off. The server instructions give the real costs and the workflow
  (search, show the delivered price, `get_buy_link` on request). `DAILY_CREDIT_BUDGET`, when set, caps MCP calls too.
- **Errors the model can act on.** A bad PIN or query, an unknown listing id, a busy server or a used-up budget
  come back as tool errors with a code (`invalid_pincode: ...`) before anything is spent. A search that fails
  halfway still returns what it found, marked "Search incomplete".
- **Honest output.** A spelling correction is stated ("Read \"dollo 650\" as Dolo 650"), estimated pack sizes
  are marked `~`, and swaps always carry "Same salt, strength and form. Ask a doctor or pharmacist before
  switching brands."
- **Annotations and progress.** `cache_lab` and `cache_stats` are read-only. The searches are open-world,
  non-destructive and idempotent. Both searches send MCP progress notifications for each lookup and stage.
- **Clean stdout.** The protocol runs on a private copy of stdout. Console prints from the cache and library
  warnings go to stderr, which MCP clients keep as the server log.

**Add the public connector:**

- **Claude** (claude.ai or Claude Desktop): Settings → Connectors → Add custom connector → URL
  `https://pharmawatch-api-zmwy.onrender.com/mcp`.
- **Cursor** (`~/.cursor/mcp.json`) or any client that takes a URL:
  `{"mcpServers": {"pharmawatch": {"url": "https://pharmawatch-api-zmwy.onrender.com/mcp"}}}`
- The free host sleeps when idle; the first call after that can take about a minute.

**Run it locally instead** (`claude_desktop_config.json`; use your own absolute path and Python):

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

The server reads `.env` from the repo root, whatever directory the client starts it in. Redis must be running
(`docker compose up -d redis`, or the full stack).

**Code layout** (`pharmawatch_mcp/`; `mcp_server.py` is only the stdio launcher):

| Module | Job |
|---|---|
| `app.py` | The server instance and the instructions the model reads |
| `models.py` | Typed inputs and outputs; each output model is a tool's `outputSchema` |
| `convert.py` | The API's result dicts → output models (links, plans, spelling, savings) |
| `render.py` | Output models → compact Markdown |
| `tools.py` | The five tools, progress reporting, error mapping |
| `prompts.py` | `compare_medicine`, `plan_my_prescription` |
| `schemas.py` | `$ref` inlining for clients that don't resolve `$defs` |
| `stdio.py` / `remote.py` | Local transport / Streamable HTTP at `/mcp` on the API (`MCP_ALLOWED_HOSTS` for Host checks) |

**Codex CLI or IDE (local Windows setup):** Install `requirements.txt` into this project's `.venv`,
then register the same stdio server from PowerShell in the repo root. See the
[Codex MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) for other platforms.

```powershell
$python = (Resolve-Path .venv\Scripts\python.exe).Path
$server = (Resolve-Path mcp_server.py).Path
codex mcp add pharmawatch -- $python $server
codex mcp get pharmawatch
```

In `~/.codex/config.toml`, add these values under the resulting `[mcp_servers.pharmawatch]` section:

```toml
default_tools_approval_mode = "writes"
tool_timeout_sec = 180
```

The approval setting prompts before `search_medicine` or `plan_prescription`, which can spend SerpApi
credits; `cache_lab` and `cache_stats` are marked read-only. The 180-second timeout covers the default
135-second prescription deadline. Raise it if `SEARCH_TIMEOUT_S` is increased. Codex stores the local
server with absolute paths, so register it again after moving the repo or rebuilding `.venv` elsewhere.

Restart the Codex IDE extension or open a new Codex session, then check `codex mcp list` or `/mcp` in
the Codex CLI. Ask “Use pharmawatch cache_stats to check Redis” for a zero-credit check, or ask
“Use pharmawatch to find the cheapest delivered price for Stamlo 5 to PIN 110001” for a live search.

**MCP Inspector:**

```bash
npx @modelcontextprotocol/inspector python mcp_server.py                     # web UI (local)
npx @modelcontextprotocol/inspector --transport http --server-url https://pharmawatch-api-zmwy.onrender.com/mcp
npx @modelcontextprotocol/inspector --cli python mcp_server.py --method tools/list
```

**Example.** Asking Claude or Codex *"Where is Telma 40 cheapest delivered to 110001, and is there a cheaper brand?"* makes
it call `search_medicine`. Real output from a cached run (links shortened):

```markdown
## Telma 40: delivered prices to PIN 110001

Cheapest delivered: **₹144.40** at 1mg (₹50 delivery · add ₹405.60 more for FREE delivery).

| # | Pharmacy | Product | Shelf price | Delivery | You pay | Arrives | Buy |
|---|---|---|---|---|---|---|---|
| 1 | 1mg | Telma 40 Tablet | ₹94.40 | ₹50 delivery · add ₹405.60 more for FREE delivery | ₹144.40 | 1-2 Days | [store search](…) · id `536999347923b066` |
| 2 | Apollo Pharmacy | Telma 40 mg Tablet 15's | ₹108.00 | ₹93.22 delivery · no free-delivery offer | ₹201.22 | 10-30 Mins / 1 Day | [store search](…) · id `d991be96b6f0bf3c` |
| 3 | Apollo Pharmacy | Telma 40 mg Tablet 30's | ₹216.50 | ₹7.08 delivery · no free-delivery offer | ₹223.58 | 10-30 Mins / 1 Day | [store search](…) · id `8bf7ca248a13cc06` |
| 4 | 1mg | Telma 40mg 30 Tablets by wellness forever | ₹189.00 | ₹50 delivery · add ₹311 more for FREE delivery | ₹239.00 | 1-2 Days | [store search](…) · id `fba8cd76406c76e2` |
| 5 | PharmEasy | Telma 40Mg Strip Of 30 Tablets | ₹166.87 | ₹130 delivery · add ₹763.13 more for FREE delivery · +₹13 platform fee | ₹309.87 | 1-2 Days | [store search](…) · id `ceea2f2e2248bcb8` |
| 6 | Medplus | Telma 40MG Tab | ₹216.72 | Delivers to PIN 110001, but delivery fee is not published | — | Same Day / Store Pickup | id `44c7115aa841ce5d` |

### Same-salt brands: Telmisartan 40mg tablet
Reference: Telma 40 mg Tablet 30's at Apollo Pharmacy, ₹223.58, ₹7.45/tablet delivered.

| Brand | Maker | Pharmacy | You pay | Per tablet | Pack | Saving | Buy |
|---|---|---|---|---|---|---|---|
| Telx 40mg | Alteus Biogenics Pvt Ltd | SastaSundar | ₹93.12 | ₹6.21 | 15 | 16.6% (₹1.24/tablet) | id `b8e4f4ac5ef71d2e` |
| Telmibless 40mg | Mankind Pharma Ltd | Truemeds | ₹108.62 | ₹7.24 | 15 | 2.8% (₹0.21/tablet) | id `144be2aedd6fe519` |
| Telmiride 40 | Unison Pharmaceuticals Pvt Ltd | 1mg | ₹72.70 | ₹7.27 | ~10 (est.) | ≈2.4% (₹0.18/tablet) | [store search](…) · id `8147a4b405166305` |

Per tablet includes delivery. ~ = pack size estimated, ≈ = saving depends on it. Same salt, strength and form. Ask a doctor or pharmacist before switching brands.
Not deliverable here right now: Cresar 40.

Buy: `product page` opens the pharmacy's own page. For an `id`, call get_buy_link with it to get that pharmacy's product page (1 SerpApi credit the first time, then cached for 24 h).

### Run
4 SerpApi lookups · 0 credits spent · 4 served from cache (4 exact, 0 semantic) · 0.2 s
```

The user picks 1mg, so Claude calls `get_buy_link("536999347923b066")`:

```markdown
**Product page** for Telma 40 Tablet at 1mg: https://www.1mg.com/drugs/telma-40-tablet-156977

0 credits spent · 0.0 s
```


---

## Tests

```bash
python scripts/test_p5_generics.py                           # 117 offline checks, 0 credits
python scripts/test_basket.py                                # 20 basket checks incl. brute force, 0 credits
python scripts/test_p4_delivery_cost.py                      # delivery rules, 0 credits
python scripts/test_api.py                                   # 54 API checks, stubbed pipeline, 0 credits
python scripts/test_mcp.py                                   # 88 MCP checks: in memory + 3 real stdio sessions, 0 credits
python scripts/test_p5_generics.py --llm "dollo 650" "Telma 40 H"          # Gemini only, 0 SerpApi credits
python scripts/test_p5_generics.py "Stamlo 5" 110001 --cache-only          # replay from Redis, 0 credits
python scripts/test_p5_generics.py "Stamlo 5" 110001                       # live run, full call log
python scripts/benchmark.py                                  # vs the pharmacies' own suggestions (live, cached = 0)
python scripts/reference_check.py                            # 15 medicines + 4 prescriptions vs Chemist180's suggestions
python scripts/live_prescription.py "Dolo 650 x30" "Stamlo 5"               # a whole prescription, live
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
  prescription.py       a whole prescription: every line's searches at once, then the basket
  basket.py             the cheapest way to buy it: offers, delivery per pharmacy subtotal, exact search
  medicines.py          what a search names: brand / salt / needs a strength, same-composition brands
  drug_db/medicines.sqlite.gz   246,046 medicines from the Indian Medicine Dataset (MIT)
notes/postal_codes_delivery_rules.json   PIN zones and delivery fees per pharmacy
api/                    FastAPI layer (SSE search, health, cache lab)
mcp_server.py           MCP stdio launcher
pharmawatch_mcp/        MCP server: 5 tools, 2 prompts, typed output; also served over HTTP at /mcp
web/                    Next.js UI
scripts/                offline tests, live replay, threshold tuning
docker-compose.yml      Redis + API + UI, with healthchecks (api/Dockerfile, web/Dockerfile)
```

---

## Known limits

- **Google Shopping coverage.** Some brands are not listed at all (Amtas 5, Telvas 40); pooling helps
  but cannot invent listings.
- **Estimated pack sizes are estimates.** They are always flagged; a pharmacy selling an unusual pack
  can still be misread.
- **Dataset age and gaps.** The dataset is a snapshot. Brands launched after it (for example Siglinu 50)
  are not recognised in titles, so they are left out rather than guessed. A medicine the index doesn't
  know still gets prices, but no alternatives.
- **Two salts per product.** The dataset stores at most two salts, so a three-salt combination is keyed
  on two. Titles still go through the combination guards (variant letters, second doses).
- **Google decides which brands appear.** Alternatives are the same-salt brands Google Shopping lists
  for our searches. A cheap brand that Google doesn't show for them is not compared; combination
  generics are the weakest case (4 of the 5 misses in the reference check).
- **Delivery fees** come from each pharmacy's published rules and can change.

---

## License

MIT
