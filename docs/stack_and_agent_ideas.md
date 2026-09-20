# 🧱 The Stack + 5 Out-of-the-Box Agent Ideas

---

## Part 1: The Combined Stack Strategy

**Yes — building both as one submission is not just possible, it's smarter.**

Here's the architecture story you tell:

```
┌─────────────────────────────────────────────────────┐
│              serpapi-production-stack               │  ← your open-source repo
│                                                     │
│  Layer 1: serpapi-distiller                         │
│  → Cleans raw SerpApi JSON                          │
│  → Removes noise (ads, panels, duplicates)          │
│  → Outputs token-budgeted Markdown for LLMs         │
│                                                     │
│  Layer 2: serpapi-cache (Redis backend)             │
│  → Semantic similarity check (embeddings)           │
│  → Cache hit → return distilled result from Redis   │
│  → Cache miss → call SerpApi → distill → cache      │
│                                                     │
│  Layer 3: AI Agent (your demo application)          │
│  → Uses the stack above                             │
│  → Solves a real novel problem                      │
│  → Proves the libraries work in production          │
└─────────────────────────────────────────────────────┘
```

**Why this wins the Open-Source track:**
- The stack itself (layers 1+2) is the open-source contribution
- The agent (layer 3) is the working demo — judges see it in action
- You're submitting infrastructure + proof-of-concept in one repo
- Josef sees clean code + Docker. Pranav sees credits saved. Tomas sees distilled context. Adarsh sees shipped product.

**One repo structure:**
```
serpapi-production-stack/
├── serpapi_distiller/     ← pip-installable library
├── serpapi_cache/         ← pip-installable library (Redis + semantic)
├── agent_demo/            ← the AI agent using both
├── docker-compose.yml     ← Redis + agent, one command startup
├── README.md              ← the money document
└── pyproject.toml
```

---

## Part 2: 5 Genuinely Out-of-the-Box Agent Ideas

> These are NOT research assistants, fact-checkers, or job analyzers. These are **real workflows people pay serious money for** — now automated.

---

### 🔥 1. `TenderHawk` — Government Tender Intelligence Agent

**The real problem:**
India publishes thousands of government tenders daily on GeM, CPPP, state portals. SMBs and startups are eligible for ₹crore contracts but miss them because discovery is a nightmare — portals are ugly, search is broken, and nobody monitors 24/7. Companies pay consultants ₹20,000–50,000/month just to track tenders manually.

**What the agent does:**
- Takes: your company profile (sector, capabilities, location, size)
- Searches: Google for new tender announcements across government portals
- Distils: strips boilerplate, extracts deadline / budget / eligibility
- Scores: relevance match against your profile (0–100)
- Outputs: daily digest email / Slack notification with ranked tenders + bid-or-skip recommendation

**SerpApi engines:** `google` (site:gem.gov.in, site:eprocure.gov.in), `google_news`
**What makes it novel:** No AI tool does this. Existing tools are manual dashboards. This is fully autonomous.
**Stack usage:**
- Cache: same tender search won't refire for 6 hrs
- Distiller: strips government portal boilerplate → clean eligibility text for LLM

---

### ⚡ 2. `SEO Arbitrage Agent` — Find What Competitors Rank For (That You Don't)

**The real problem:**
SEO agencies charge ₹30,000–1,00,000/month to do competitive keyword gap analysis. The workflow is: search what your competitor ranks for → find where you don't rank → prioritize content to create. This is 100% manual today.

**What the agent does:**
- Takes: your domain + up to 3 competitor domains
- Searches: Google for 50+ industry queries, checks who appears where
- Builds: keyword gap map — what competitors own that you're invisible on
- Reasons: why each gap exists (content missing? weak backlinks? wrong intent?)
- Outputs: prioritized content brief with estimated traffic opportunity

**SerpApi engines:** `google` (with `gl`, `hl` params for India targeting), `google_news`
**What makes it novel:** This replaces Ahrefs/SEMrush workflows (₹10,000+/month tools) for free. Fully autonomous, no human needed.
**Stack usage:**
- Cache: competitor search results cached by query — hundreds of searches, saved credits
- Distiller: strips SERP furniture → just organic rankings for analysis

---

### 💊 3. `PharmaWatch` — Drug Price & Availability Monitoring Agent

**The real problem:**
Medicine prices in India vary 200–400% across platforms (1mg, PharmEasy, Netmeds, local chemists). Patients with chronic conditions (diabetes, BP, thyroid) overpay thousands per year simply because they don't know where to buy. Generic alternatives exist but are invisible to most patients.

**What the agent does:**
- Takes: a prescription or list of medicines
- Searches: Google Shopping + web for prices across all major Indian pharma platforms
- Tracks: price changes over time (via Redis cache + delta comparison)
- Finds: bioequivalent generics at fraction of cost (Google Scholar for drug name lookup)
- Alerts: when price spikes or cheaper alternative found

**SerpApi engines:** `google_shopping`, `google`, `google_scholar`
**What makes it novel:** No existing tool does cross-platform Indian pharma price intelligence + generic alternatives together. This is life-changing for 100M+ chronic disease patients.
**Stack usage:**
- Cache: medicine prices cached per-day, price delta alerts when cache updates
- Distiller: cleans shopping results → only price, platform, availability fields

---

### 📜 4. `CitationSheriff` — Academic Citation Integrity Verifier

**The real problem:**
Academic papers frequently misrepresent what cited sources actually say. A study gets cited as "proving X" when it actually says "X is inconclusive." This is rampant in medical, nutrition, and social science literature. Researchers manually check citations — nobody has automated it.

**What the agent does:**
- Takes: a claim from a paper + its citation (DOI or paper title)
- Fetches: the cited paper via Google Scholar
- Extracts: actual conclusions from the abstract / full text
- Compares: what the citing paper says vs. what the source actually concludes
- Verdict: ACCURATE / OVERSTATED / CONTRADICTED / UNVERIFIABLE

**SerpApi engines:** `google_scholar`, `google`
**What makes it novel:** Zero tools exist that do citation-level verification. Academic integrity software (iThenticate, Turnitin) only catches copy-paste — not semantic misrepresentation.
**Stack usage:**
- Cache: Scholar searches for the same paper cached indefinitely (papers don't change)
- Distiller: extracts only abstract + conclusion sections from Scholar results

---

### 📰 5. `NewsArb` — Global News Arbitrage Agent for Indian Journalists

**The real problem:**
Stories that are huge internationally often take 24–72 hours to get picked in Indian media. First-movers get massive traffic. Journalists and bloggers who catch these stories early win. But monitoring 50 international news sources manually is impossible.

**What the agent does:**
- Monitors: Google News for 20+ international sources (BBC, Reuters, AP, Guardian)
- Compares: same topic search on Indian news sources
- Calculates: "Coverage Gap Score" — how big is the story globally vs. how little covered in India
- Ranks: top 10 stories with highest arbitrage potential (big internationally, invisible in India)
- Outputs: daily briefing with story angle suggestions tailored for Indian audience

**SerpApi engines:** `google_news` (with `gl=us`, `gl=gb`, `gl=in` to compare geographies)
**What makes it novel:** This is a genuine intelligence operation. News agencies pay analysts to do this. Now it's automated. The `gl` parameter in SerpApi makes this uniquely possible.
**Stack usage:**
- Cache: international news cached per-topic per-6hrs, Indian news checked fresh every run
- Distiller: strips news boilerplate → just headline, source, date, snippet for comparison

---

## My Recommendation

**Build `TenderHawk` or `PharmaWatch` as the demo agent.**

| | TenderHawk | PharmaWatch |
|---|---|---|
| **India relevance** | 🔥🔥🔥🔥 | 🔥🔥🔥🔥🔥 |
| **Novelty** | No existing tool | No existing tool |
| **Judge appeal** | Pranav (business value) | Adarsh (practical everyday) |
| **Demo wow factor** | "I found a ₹50L contract" | "I saved ₹800/month on meds" |
| **Complexity** | Medium | Medium |

**`PharmaWatch` wins on demo-ability.** The moment you show: *"Here's a prescription → here's where to buy each medicine cheapest → here's the generic alternative"* — that's the 90-second wow moment that wins hackathons.

---

## Final Architecture Decision

```
Repo: serpapi-production-stack
│
├── Core libraries (open-source contribution)
│   ├── serpapi_distiller/   ← context cleaning
│   └── serpapi_cache/       ← Redis semantic cache
│
└── Demo agent: PharmaWatch (or TenderHawk)
    └── Uses both libraries end-to-end
        Shows real output in Streamlit UI
        docker-compose up → runs everything
```

**One repo. Two libraries. One killer demo. Three judge criteria hit in one shot.**
