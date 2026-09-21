# PharmaWatch — Implementation Plan

> Cross-platform Indian pharma price intelligence + generic alternatives.
> Built on top of the existing `serpapi_cache` library already in this repo.

> [!IMPORTANT]
> **Design decisions locked (OQ1–OQ3):** See bottom of doc for rationale.

---

## What We're Building

A Streamlit web app where a user inputs a medicine name **or uploads a prescription image or speaks it aloud**,
and gets back:

1. Prices across Indian platforms (1mg, PharmEasy, Netmeds, Apollo)
2. Cheapest option highlighted
3. Bioequivalent generic alternative — AI predicts from a doctor-verified composition document, then cross-verifies with Google Scholar. If confidence is below threshold, returns "no verified alternative found" rather than hallucinate.
4. Price change alert if the same medicine was searched before (Redis delta)

**SerpApi engines used:** `google_shopping`, `google`, `google_lens` (prescription scan)

---

## Repo Structure After Build

```
serpapi-production-stack/
├── serpapi_cache/          ← already exists ✅
├── pharmawatch/            ← new: the agent
│   ├── __init__.py
│   ├── search.py           ← SerpApi calls (shopping + lens + scholar)
│   ├── distiller.py        ← clean raw JSON → price/platform/availability dicts
│   ├── comparator.py       ← rank platforms, compute delta vs cached price
│   ├── generics.py         ← 3-step generic finder pipeline
│   ├── agent.py            ← orchestrator: ties all modules together
│   └── drug_db/
│       └── compositions.md  ← curated brand→composition reference (MD for LLM context)
├── app.py                  ← Streamlit UI entry point
├── docker-compose.yml      ← Redis + app, one command
├── requirements.txt        ← update with new deps
└── docs/
    └── pharmawatch_implementation_plan.md  ← this file
```

---

## To-Do List (Ordered)

### Phase 0 — Drug Composition Database (`pharmawatch/drug_db/`)

Foundation for generic matching. Stored as Markdown because:
- LLMs consume MD naturally as context (better than parsing JSON structure)
- Human-readable and easy to extend
- Simple regex/section parser handles programmatic lookup

- [ ] **P0.1** Create `compositions.md` with this structure per medicine:
  ```markdown
  ## Metformin 500mg
  - **Active Ingredient:** Metformin Hydrochloride 500mg
  - **Drug Class:** Biguanide antidiabetic
  - **Known Generics:** Glyciphage 500, Gluconorm 500, Obimet 500
  ```

- [ ] **P0.2** Seed initial data for the 20 most common chronic disease medicines in India
  - Diabetes: Metformin, Glimepiride, Januvia
  - BP: Amlodipine, Telmisartan, Atenolol
  - Thyroid: Levothyroxine
  - Cholesterol: Atorvastatin, Rosuvastatin
  - Pain/Fever: Paracetamol, Ibuprofen, Diclofenac
  - **Critical:** demo medicines (Metformin, Atorvastatin, Levothyroxine) must be in the file before Phase 9

- [ ] **P0.3** AI fallback — when a medicine is NOT in `compositions.md`:
  - Feed the medicine name to LLM with narrow prompt: *"What is the active ingredient (INN) in {medicine}? Return only the INN name and dosage, nothing else."*
  - Use as fallback only — always goes through Scholar verification (P5.2) before showing to user
  - Flag result as `verified: false` in the UI

---

### Phase 1 — Foundation

- [ ] **P1.1** Add new dependencies to `requirements.txt`
  - `streamlit>=1.35.0`
  - `openai>=1.0.0` (or `google-generativeai` — for LLM reasoning step)
  - `pandas>=2.0.0`

- [ ] **P1.2** Create `pharmawatch/` package with empty `__init__.py`

- [ ] **P1.3** Set up `.env` with required keys
  - `SERP_API_KEY` (already exists)
  - `OPENAI_API_KEY` or `GEMINI_API_KEY` (for generic reasoning)

---

### Phase 2 — Search Layer (`pharmawatch/search.py`)

This module wraps `SerpApiCache.search()` with PharmaWatch-specific query patterns.

- [ ] **P2.1** `search_prices(medicine_name: str) -> dict`
  - Engine: `google_shopping`
  - Query: `"{medicine_name} tablet price India"`
  - Params: `gl=in`, `hl=en`
  - TTL: `86400` (24 hours — prices cached per day)
  - Returns: raw SerpApi shopping JSON

- [ ] **P2.2** `scan_prescription_image(image_url: str) -> list[str]`
  - Engine: `google_lens`
  - Passes image URL to SerpApi Google Lens endpoint
  - Parses the returned text/visual matches to extract medicine names
  - Returns: list of medicine name strings identified in the image

- [ ] **P2.3** `search_platform_price(medicine_name: str, platform: str) -> dict`
  - Engine: `google`
  - Query: `"{medicine_name} price site:{platform_domain}"`
  - TTL: `86400`
  - Use this as fallback if Shopping results miss a platform

---

### Phase 3 — Distiller (`pharmawatch/distiller.py`)

Extract only what's needed from raw SerpApi JSON.

- [ ] **P3.1** `distill_shopping_results(raw: dict) -> list[dict]`
  - Input: raw `google_shopping` response
  - Output: list of `{platform, price_inr, medicine_name, availability, link}`
  - Filter: keep only results whose source matches known Indian pharma domains
    (`1mg.com`, `pharmeasy.in`, `netmeds.com`, `apollopharmacy.in`, `medplusbazaar.com`)
  - Strip: ads, irrelevant products, international sellers

- [ ] **P3.2** `distill_scholar_results(raw: dict) -> list[dict]`
  - Input: raw `google_scholar` response
  - Output: list of `{title, snippet, generic_name_hint}`
  - Keep only first 3 results (enough for LLM to reason on)

---

### Phase 4 — Comparator (`pharmawatch/comparator.py`)

Price ranking and delta detection.

- [ ] **P4.1** `rank_by_price(results: list[dict]) -> list[dict]`
  - Sort distilled results by `price_inr` ascending
  - Return ranked list with `rank` field added

- [ ] **P4.2** `compute_price_delta(medicine_name: str, current_price: float, backend) -> dict`
  - Check Redis for previously stored price for this medicine
  - If exists: compute `delta = current - previous`, `delta_pct`
  - If no prior record: store current price, return `{delta: None, is_first_check: True}`
  - If `delta_pct > 10%`: flag as `price_spike = True`
  - Store new price with key `pharmawatch:price:{medicine_slug}`

---

### Phase 5 — Generic Finder (`pharmawatch/generics.py`)

Three-step pipeline. Hallucination is not an option — if we can't verify, we say so.

**Step 1 — AI prediction from verified document:**
- [ ] **P5.1** `predict_generic(medicine_name: str) -> dict`
  - Pass `compositions.json` content + medicine name to LLM as context
  - Prompt is narrow: *"Based only on the provided document, what is the active ingredient (INN) and known generic equivalents of {medicine}? If the document does not contain this medicine, return null."*
  - LLM must answer from the document only — no open-ended generation
  - Returns: `{generic_name, active_ingredient, confidence_score, source: "db"}` or `None`

**Step 2 — Google Scholar cross-verification:**
- [ ] **P5.2** `verify_via_scholar(medicine_name: str, predicted_generic: str) -> dict`
  - Engine: `google_scholar`
  - Query: `"{predicted_generic} bioequivalent {medicine_name}"`
  - Parse top 3 results for confirmation signal
  - Compute a `scholar_confidence` score (0.0–1.0) based on how many results confirm the equivalence
  - Returns: `{scholar_confidence, supporting_results: [...]}`

**Step 3 — Threshold gate (no hallucination path):**
- [ ] **P5.3** `resolve_generic(medicine_name: str) -> dict`
  - Call P5.1 → get AI prediction
  - If prediction is `None` → immediately return `{found: False, reason: "not in verified database"}`
  - Call P5.2 → get Scholar confidence
  - Combined confidence = weighted avg of AI confidence + scholar_confidence
  - **Threshold: 0.80** — if combined score < 0.80 → return `{found: False, reason: "insufficient evidence"}`
  - If >= 0.80 → return `{found: True, generic_name, active_ingredient, confidence, verified: True}`
  - The UI shows result only when `found: True`; otherwise shows a clear "No verified alternative found" message

- [ ] **P5.4** `search_generic_price(generic_name: str) -> list[dict]`
  - Only called if P5.3 returns `found: True`
  - Call `search.search_prices(generic_name)`, distill and rank
  - Returns ranked price list for the verified generic

---

### Phase 6 — Agent Orchestrator (`pharmawatch/agent.py`)

- [ ] **P6.1** `run(medicine_name: str) -> dict` — main entry point
  ```
  1. search_prices(medicine_name)     → raw shopping JSON
  2. distill_shopping_results(raw)    → cleaned price list
  3. rank_by_price(cleaned)           → sorted list
  4. compute_price_delta(...)         → delta info
  5. resolve_generic(medicine_name)   → verified generic or {found: False}
  6. if found: search_generic_price() → generic price list
  7. return full report dict
  ```

- [ ] **P6.2** Report dict schema:
  ```python
  {
    "medicine": str,
    "prices": [{"platform", "price_inr", "link", "rank"}],
    "cheapest": {"platform", "price_inr", "link"},
    "price_delta": {"delta_inr", "delta_pct", "price_spike", "is_first_check"},
    "generic": {
      "name": str,
      "prices": [{"platform", "price_inr", "link", "rank"}],
      "cheapest": {"platform", "price_inr", "link"},
      "savings_vs_branded_inr": float,
    }
  }
  ```

---

### Phase 7 — Streamlit UI (`app.py`)

- [ ] **P7.1** Input section — three ways to enter a medicine:
  - **Text:** type medicine name directly
  - **Image:** upload prescription photo → passed to Google Lens API → names extracted
  - **Voice:** browser speech-to-text (`st.audio_input` or JS Web Speech API) → text fed into same pipeline
  - All three converge to the same `agent.run(medicine_name)` call

- [ ] **P7.2** Results section (shown after search)
  - Price comparison table: platform | price | link | cheapest badge
  - Price delta banner: green if price dropped, red if spike detected
  - Generic alternative card:
    - Generic name + composition
    - `verified by doctor` badge (green) or `AI estimate` badge (yellow) based on `verified` flag
    - Cheapest generic price + savings amount vs. branded
  - Cache status badge: show HIT/MISS and API credits saved

- [ ] **P7.3** Sidebar
  - Cache stats (hits, misses, hit rate) from `SerpApiCache.get_stats()`
  - Redis connection status indicator
  - Drug DB coverage: how many medicines are in `compositions.json`

---

### Phase 8 — Docker + Infra

- [ ] **P8.1** Create `docker-compose.yml`
  ```yaml
  services:
    redis:
      image: redis:7-alpine
      ports: ["6379:6379"]
    app:
      build: .
      ports: ["8501:8501"]
      depends_on: [redis]
      env_file: .env
  ```

- [ ] **P8.2** Create `Dockerfile`
  - Base: `python:3.11-slim`
  - Install deps, copy code, `CMD streamlit run app.py`

- [ ] **P8.3** Verify `docker-compose up` starts everything cleanly

---

### Phase 9 — Polish and Demo Prep

- [ ] **P9.1** Test with real medicines: `Metformin 500mg`, `Atorvastatin 10mg`, `Levothyroxine 50mcg`
- [ ] **P9.2** Verify Redis delta works: search same medicine twice, confirm delta shows
- [ ] **P9.3** Update `README.md` with PharmaWatch demo section + GIF/screenshot
- [ ] **P9.4** Verify cache hit rate on repeated searches (target: >80% in demo run)

---

## Design Decisions (Locked)

**OQ1 — Generic matching strategy:** ✅ LOCKED
- Build a curated `drug_db/compositions.json` verified by doctors as the primary source
- AI (LLM) is fallback only when a medicine is not in the DB
- AI results shown with `AI estimate` label, DB results shown with `verified` label
- This makes the product medically credible and the open-source contribution tangible (anyone can contribute to the drug DB)

**OQ2 — Price delta Redis namespace:** ✅ LOCKED
- Separate key namespace `pharmawatch:price:*` in the same Redis instance
- Serves real purpose: tracks price history per medicine across days, fires spike alerts

**OQ3 — Prescription input:** ✅ LOCKED
- Three input modes: text, image (Google Lens API via SerpApi), voice (speech-to-text)
- All three converge to the same agent pipeline
- Google Lens handles prescription photo → medicine name extraction

---

## What Already Exists (No Rebuild Needed)

| Component | Status |
|---|---|
| `serpapi_cache.SerpApiCache` | Done — semantic cache with Redis/in-memory |
| `serpapi_cache.RedisBackend` | Done |
| `serpapi_cache.InMemoryBackend` | Done |
| Embedding model integration | Done (`all-MiniLM-L6-v2`) |
| `.env` setup | Done |

Everything in Phases 0–9 is new work except the cache layer.

---

## Critical Review — Risks and Improvements

### Technical Risks (Fix Before Building)

**R1 — Google Lens does not do OCR.**
SerpApi's Lens endpoint returns visually similar images, not extracted text. It cannot read medicine names off a prescription photo. The prescription image feature needs a different approach: use Google Cloud Vision API (free tier: 1000 calls/month) for OCR, or as a simpler fallback, accept image upload and extract text client-side using Tesseract.js. Do not build P2.2 as planned — it will not work.

**R2 — LLM confidence scores are unreliable.**
P5.1 asks the LLM to return a `confidence_score`. LLMs do not produce calibrated probabilities. Instead: use structured output (JSON mode) and derive confidence from whether the LLM could find the medicine in the document at all. If it found it → high confidence. If it's reasoning beyond the document → block it with a strict system prompt. Drop the numeric confidence from P5.1; gate purely on `found_in_document: true/false` from the LLM, then let Scholar confidence be the numeric gate.

**R3 — Price parsing will break.**
Google Shopping returns prices in inconsistent formats: `"₹45.50"`, `"Rs 45"`, `"45.50"`, `"MRP ₹120"`. The distiller needs a robust price extraction regex before any ranking. Missing this means `rank_by_price` will fail silently or sort wrong.

**R4 — compositions.md lookup needs fuzzy matching.**
A user types `"metformin"` but the file has `"Metformin 500mg"`. Exact string lookup will miss it. Add case-insensitive substring match when parsing the MD sections. Without this, the DB is unreliable for the demo.

**R5 — compositions.md will grow — context window cost.**
Passing the entire file to the LLM (P5.1) works fine at 20 medicines (~2KB). At 200 medicines it becomes expensive and slow. For the hackathon this is fine, but note it as a known scaling limit.

**R6 — Voice input (st.audio_input) requires Streamlit 1.31+.**
Confirm the version is pinned correctly and test it — browser microphone access requires HTTPS in production. For the hackathon localhost demo, HTTP is fine.

---

### Judge-Facing Improvements

**J1 — The 90-second demo script is not planned.**
For the hackathon, judges see a live demo. Plan the exact sequence: type `Metformin 500mg` → show price table → show delta (run it twice) → show generic `Glyciphage 500` at ₹X cheaper. Rehearse this flow and make sure all three medicines are in the DB.

**J2 — Show savings in rupees prominently.**
The `savings_vs_branded_inr` field is the emotional hook of the whole product. Make it the largest number on the screen. "You save ₹840/month" beats a table of prices every time.

**J3 — The "No verified alternative found" case also needs to look good.**
If the threshold gate fires and returns nothing, the UI should explain why clearly — not show a blank card. Something like: *"We couldn't verify a safe generic alternative for this medicine. Consult your pharmacist."* This actually demonstrates the anti-hallucination design to judges.

**J4 — Cache hit demo is underplanned.**
P9.4 just says "verify cache hit rate." For judges, make the cache hit visible and satisfying: show "Fetched from cache (saved 1 API credit)" with a timestamp of when the price was last fetched. This is the live proof that `serpapi_cache` works.
