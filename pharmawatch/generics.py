"""
generics.py — Cheaper generic alternatives from drug_db/compositions.md.

Flow for a search like "Dolo 650" at PIN 110001:
  1. Gemini reads compositions.md and returns the 3 best substitutes for the searched medicine
     (a listed brand or an entry name) from the same entry — e.g. Calpol 650, Crocin 650, Pacimol 650.
     Brands listed together are trusted as equivalent generics; anything Gemini names outside
     that entry is dropped. Answers are cached per query.
  2. Search the 3 substitutes by exact name (1 google_shopping call each, cached 24h, never
     served another medicine's results). Pool the listings of every search in the run — a
     brand's own search often misses it while another search has it — and keep only listings
     whose title really is that brand + strength (look-alike combinations such as AT / Bis /
     '5/50mg' rejected), with delivery cost added.
  3. Compare per-tablet landed price (delivery included) against the searched brand's
     cheapest deliverable listing. A pack size missing from a title is estimated from the
     brand's other listings and flagged (pack_estimated / estimated); with no usable pack
     size, total landed price is compared.
  4. Resolve the direct 'Visit Site' link (1 extra call) only for alternatives that are cheaper.

Steps run in parallel in pipeline.py; this module holds the matching and comparison logic.
"""

import hashlib
import math
import re
import warnings
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

from pharmawatch.comparator import rank_by_landed_price
from pharmawatch.distiller import distill_shopping_results

_COMPOSITIONS_PATH = Path(__file__).parent / "drug_db" / "compositions.md"
_DELIVERABLE = ("free", "charged")

_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[a-z]+")

# Dropped before matching: units, dosage-form words, search noise, salt suffixes.
_FILLER = {
    "mg", "mcg", "ml", "iu", "price", "buy", "online",
    "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps",
    "hydrochloride", "hcl",
}

# Variant markers: a title carrying one of these that the brand name doesn't is a different
# product ("Pan 40" vs "Pan D", "Glyciphage 500" vs "Glyciphage SR 500", "Telma 40" vs "Telma 40 H",
# "Amlokind 5" vs "Amlokind AT", "Stamlo 5" vs "Stamlo Bis 5" / "Stamlo Beta" / "Met Stamlo").
_VARIANT_MARKERS = {
    "sr", "xr", "xl", "er", "cr", "mr", "pr", "od", "dsr", "d", "ds", "l", "lc", "m", "p", "sp",
    "h", "am", "at", "ct", "mt", "tm", "tl", "ln", "ls", "cv", "oz", "g", "gm", "mf", "f", "t", "ez",
    "asp", "av", "xm", "bis", "beta", "met", "trio", "plus", "forte", "duo", "chrono",
    "kid", "kids", "junior",
}

# "5/50mg", "5 mg / 12.5 mg" — two strengths in one title.
_STRENGTH_PAIR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mg|mcg|g)?\s*/\s*(\d+(?:\.\d+)?)")
# "40Mg 8Mg" — every dose written with a unit.
_UNIT_STRENGTH_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:mg|mcg)\b")
# The pharmacy '1mg' in titles ("... Substitutes | 1mg", "Tata 1mg") is not a dose.
_SITE_1MG_RE = re.compile(r"(\|\s*|tata\s+)1mg\b|\b1mg\.com")
# Words that may follow a brand name without making it a different product.
_NEUTRAL_AFTER_BRAND = {"for", "by", "and", "with", "new", "the", "of", "in", "from", "s", "ec",
                        "pack", "strip", "box"}

# Non-tablet forms that share a brand name (e.g. "Combiflam Suspension").
_OTHER_FORMS = {"suspension", "syrup", "injection", "drops", "gel", "cream", "spray", "ointment", "sachet"}

_PACK_PATTERNS = [
    re.compile(p) for p in (
        r"strip\s*of\s*(\d+)",
        r"pack\s*of\s*(\d+)\s*(?:tablets?|capsules?|tabs?|caps?)\b",
        r"(?<![\d.])(\d+)\s*(?:tablets?|capsules?|tabs?|caps?)\b",
        r"(?<![\d.])(\d+)\s*'\s*s\b",
        r"(?<![\d.])(\d+)s\b",
        r"pack\s*-\s*(\d+)",
        r"(?:tablets?|capsules?|tabs?|caps?)\s+(\d+)\s*$",   # Truemeds: 'Amlokind 5 Tablet 15'
    )
]

# An estimated pack is used only if the implied shelf price per tablet stays within this band
# of the brand's median per-tablet price from listings that state their pack size.
_ESTIMATE_BAND = (0.5, 2.0)


def _tokens(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(str(text).lower()) if t not in _FILLER]


# ─────────────────────────────────────────────
# compositions.md
# ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_compositions() -> List[dict]:
    """Parse compositions.md → [{name, active_ingredient, drug_class, brands}, ...]."""
    entries, current = [], None
    for line in _COMPOSITIONS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("## "):
            current = {"name": line[3:].strip(), "active_ingredient": "", "drug_class": "", "brands": []}
            entries.append(current)
        elif current is None:
            continue
        elif line.startswith("- **Active Ingredient:**"):
            current["active_ingredient"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Drug Class:**"):
            current["drug_class"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Known Generics:**"):
            current["brands"] = [b.strip() for b in line.split(":**", 1)[1].split(",") if b.strip()]
    return entries


def _salt_keys(entry: dict) -> List[FrozenSet[str]]:
    """'Aspirin 75mg EC (Enteric Coated)' → {aspirin, 75, ec} and {aspirin, 75}."""
    tokens = frozenset(_tokens(re.sub(r"\(.*?\)", "", entry["name"])))
    return [tokens, tokens - {"ec"}]


@lru_cache(maxsize=1)
def _indexes() -> Tuple[Dict[FrozenSet[str], Tuple[dict, str]], Dict[FrozenSet[str], dict]]:
    brand_index, salt_index = {}, {}
    for entry in load_compositions():
        for brand in entry["brands"]:
            brand_index.setdefault(frozenset(_tokens(brand)), (entry, brand))
        for key in _salt_keys(entry):
            salt_index.setdefault(key, entry)
    return brand_index, salt_index


MAX_ALTERNATIVES = 3


def find_composition(query: str, use_llm: bool = True) -> Optional[dict]:
    """
    Up to MAX_ALTERNATIVES substitute medicines for `query`, taken from compositions.md.
      gemini : reads compositions.md, finds the entry holding the searched medicine (a listed brand
               or the entry's own name) and returns the 3 best substitutes from that same entry.
               One call per distinct query, then cached in Redis.
      exact  : fallback when Gemini is off or unavailable — the query must be a listed brand or
               entry name (case, hyphens, 'mg', 'tablet', word order ignored); first 3 other brands.
    Returns {"entry", "matched_as": "brand" | "salt", "matched_brand", "alternatives",
             "matched_by": "gemini" | "exact", "reason"} or None.
    """
    if not _tokens(query):
        return None
    if use_llm:
        match = _gemini_match(query)
        if match is not _GEMINI_UNAVAILABLE:
            return match
    return _exact_match(query)


def _exact_match(query: str) -> Optional[dict]:
    key = frozenset(_tokens(query))
    brand_index, salt_index = _indexes()
    if key in brand_index:
        entry, brand = brand_index[key]
        reason = "brand listed in compositions.md"
    elif key in salt_index:
        entry, brand = salt_index[key], None
        reason = "name of a compositions.md entry"
    else:
        return None
    alternatives = [b for b in entry["brands"] if b != brand][:MAX_ALTERNATIVES]
    return {"entry": entry, "matched_as": "brand" if brand else "salt", "matched_brand": brand,
            "alternatives": alternatives, "matched_by": "exact", "reason": reason}


# ─────────────────────────────────────────────
# Gemini: search → 3 substitutes (compositions.md is the only allowed answer set)
# ─────────────────────────────────────────────

_DECISION_TTL = 30 * 86_400  # substitutes don't change; the key includes the file + prompt hash
_GEMINI_UNAVAILABLE = object()

_DECISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "searched_brand": {"type": "STRING", "nullable": True},
        "alternatives": {"type": "ARRAY", "items": {"type": "STRING"}},
        "reason": {"type": "STRING"},
    },
    "required": ["searched_brand", "alternatives", "reason"],
}

_PROMPT = """You are a pharmacist finding substitutes for a medicine searched on an Indian pharmacy site.
The catalogue below is the ONLY trusted source: each entry lists brands with the same composition,
strength and release type, which can replace each other.

Catalogue (entry | active ingredient | substitutable brands):
{catalogue}

Search: "{query}"

1. Find the entry containing the searched medicine: one of its brands, or the entry's own generic name.
2. Return up to {n} brands from THAT SAME entry that best substitute for it, best first, spelled exactly
   as in the catalogue. Never include the searched brand itself. Never take brands from another entry.
3. searched_brand: the catalogue brand the search names (exact catalogue spelling), or null if the
   search is the generic name.
4. A brand with an extra suffix (H, AM, D, M, L, Plus, Forte, SR, MR...) that the entry does not list is a
   different medicine ("Telma 40 H" is not "Telma 40"). If the searched medicine is not in the catalogue,
   return an empty alternatives list. Never guess.
5. reason: one short sentence."""


def _decision_version() -> str:
    """Changes when compositions.md or the prompt changes, so stale cached decisions are ignored."""
    return hashlib.sha256(_COMPOSITIONS_PATH.read_bytes() + _PROMPT.encode()).hexdigest()[:12]


def _decision_store():
    """Redis backend of the shared SerpApi cache, or None in passthrough mode."""
    from pharmawatch.search import _get_cache
    return _get_cache(verbose=False).backend


def validate_decision(decision: dict, query: str = "") -> Optional[dict]:
    """
    Keep only what compositions.md backs: every alternative must be a listed brand of the same entry
    as the searched brand (or as each other), never the searched brand itself, at most 3.
    Rejects the answer when the query carries a variant marker the entry never uses ('Telma 40 H').
    """
    brand_index, _ = _indexes()

    def lookup(name):
        return brand_index.get(frozenset(_tokens(name or "")))

    searched = lookup(decision.get("searched_brand"))
    alts = [hit for hit in map(lookup, decision.get("alternatives") or []) if hit]
    entry = searched[0] if searched else (alts[0][0] if alts else None)
    if entry is None:
        return None

    searched_brand = searched[1] if searched else None
    alternatives = []
    for alt_entry, brand in alts:
        if alt_entry is entry and brand != searched_brand and brand not in alternatives:
            alternatives.append(brand)
    alternatives = alternatives[:MAX_ALTERNATIVES]

    entry_tokens = set(_tokens(" ".join([entry["name"], *entry["brands"]])))
    if not alternatives or (set(_tokens(query)) & _VARIANT_MARKERS) - entry_tokens:
        return None
    return {"entry": entry, "matched_as": "brand" if searched_brand else "salt",
            "matched_brand": searched_brand, "alternatives": alternatives,
            "matched_by": "gemini", "reason": decision.get("reason", "")}


def _gemini_match(query: str):
    """validate_decision() result, None if not in compositions.md, or _GEMINI_UNAVAILABLE."""
    from pharmawatch.gemini import GeminiError, generate_json

    normalized = " ".join(sorted(set(_tokens(query))))
    cache_key = "gemini-alts:" + hashlib.sha256(f"{_decision_version()}|{normalized}".encode()).hexdigest()[:16]
    store = _decision_store()

    decision = store.get_by_key(cache_key) if store else None
    if decision is None:
        catalogue = "\n".join(
            f"{e['name']} | {e['active_ingredient']} | {', '.join(e['brands'])}" for e in load_compositions()
        )
        prompt = _PROMPT.format(catalogue=catalogue, query=query, n=MAX_ALTERNATIVES)
        try:
            decision = generate_json(prompt, _DECISION_SCHEMA)
        except GeminiError as e:
            warnings.warn(f"Gemini unavailable, using exact compositions.md lookup — {e}")
            return _GEMINI_UNAVAILABLE
        if store:
            # Empty embedding → exact-key entry, never returned by the similarity search.
            store.set(cache_key, decision, [], _DECISION_TTL, f"gemini-alts {normalized}")
    return validate_decision(decision, query)


# ─────────────────────────────────────────────
# Listing checks
# ─────────────────────────────────────────────

def title_matches_brand(title: str, brand: str, allow_other_forms: bool = False) -> bool:
    """
    True if a shopping title is this exact brand + strength:
    'Dolo 650mg Strip Of 15 Tablets' ✓ for 'Dolo 650'; 'Dolopar 650Mg', 'Dolo 500', 'Pan D' (for 'Pan 40') ✗.
    Combination products are rejected three ways:
      - a known variant marker the brand doesn't have: 'Amlokind AT', 'Stamlo Bis', 'Telma H'
      - a second dose: 'Stamlo Beta 5/50MG', 'Telma Az 40Mg 8Mg' ✗ for 'Stamlo 5' / 'Telma 40'
        (doses adding up to the brand's own are fine: 'Augmentin 625 (500mg/125mg)')
      - a short word straight after the brand name: 'Telma Nb 40MG', 'Telmikind Amh 40MG'
    'Pan D Capsule (30mg/40mg)' ✓ for 'Pan-D' (the brand names no strength).
    """
    brand_tokens = set(_tokens(brand))
    title_tokens = set(_tokens(title))
    if not brand_tokens <= title_tokens:
        return False
    if (title_tokens & _VARIANT_MARKERS) - brand_tokens:
        return False
    if _has_extra_strength(title, brand_tokens) or _variant_word_after_brand(title, brand):
        return False
    return allow_other_forms or not (title_tokens & _OTHER_FORMS)


def _has_extra_strength(title: str, brand_tokens: set) -> bool:
    strengths = {t for t in brand_tokens if t[0].isdigit()}
    if not strengths:
        return False
    text = _SITE_1MG_RE.sub(" ", str(title).lower())
    doses = {n for pair in _STRENGTH_PAIR_RE.findall(text) for n in pair} | set(_UNIT_STRENGTH_RE.findall(text))
    extra = {n for n in doses if not any(abs(float(n) - float(s)) < 1e-6 for s in strengths)}
    if not extra:
        return False
    total = sum(float(n) for n in extra)
    return not any(abs(total - float(s)) < 1e-6 for s in strengths)


def _variant_word_after_brand(title: str, brand: str) -> bool:
    """A short word between the brand name and its dose: 'Telma Nb 40MG' ✓, 'Crocin 650mg … View Uses' ✗."""
    brand_tokens = _tokens(brand)
    title_tokens = _tokens(title)
    words = [t for t in brand_tokens if t.isalpha()]
    strengths = {t for t in brand_tokens if t[0].isdigit()}
    if not words or not strengths or words[0] not in title_tokens:
        return False
    j = title_tokens.index(words[0])
    while j < len(title_tokens) and title_tokens[j] in brand_tokens:
        j += 1
    if j == len(title_tokens) or not strengths & set(title_tokens[j + 1:]):
        return False   # nothing left, or the dose already came before this word
    word = title_tokens[j]
    return word.isalpha() and len(word) <= 4 and word not in _NEUTRAL_AFTER_BRAND


def parse_pack_size(title: str, brand: str = "") -> Optional[int]:
    """Tablets per pack from titles like 'Strip Of 15 Tablets', '15's', '(15tab)', '(Pack-20)'."""
    text = str(title).lower()
    strength_numbers = {t for t in _tokens(brand) if t[0].isdigit()}
    for pattern in _PACK_PATTERNS:
        for m in pattern.finditer(text):
            n = m.group(1)
            if n not in strength_numbers and 1 <= int(n) <= 120:
                return int(n)
    return None


def estimate_pack_size(price_inr: float, known: List[Tuple[int, float]]) -> Optional[int]:
    """
    Pack size for a listing whose title doesn't state one, from the same brand's listings that do.
    known: [(pack_size, shelf price)] of those listings.
    Picks the pack size (among those seen for the brand) whose per-tablet price is closest to the
    brand's median per-tablet price — ₹99.80 for Telma 40 is a 15-strip (₹6.65/tab, median ₹6.43),
    not a 30 (₹3.33/tab), even though 30 is listed more often. The more common size wins a tie.
    Returns None if nothing is known or even the closest size gives an implausible price.
    """
    if not known or not price_inr:
        return None
    unit_prices = sorted(price / pack for pack, price in known)
    median = unit_prices[len(unit_prices) // 2]
    counts = Counter(pack for pack, _ in known)
    pack = min(counts, key=lambda p: (round(abs(math.log((price_inr / p) / median)), 6), -counts[p], p))
    low, high = _ESTIMATE_BAND
    return pack if low <= (price_inr / pack) / median <= high else None


def _prepare(ranked: List[dict], brand: str, allow_other_forms: bool) -> List[dict]:
    """
    Deliverable listings of this brand, each with pack_size, pack_estimated and unit_landed_cost.
    Pack sizes missing from a title are estimated from every listing of the brand (deliverable or not).
    """
    matched = [r for r in ranked if title_matches_brand(r.get("medicine_name", ""), brand, allow_other_forms)]
    parsed = [parse_pack_size(r["medicine_name"], brand) for r in matched]
    known = [(pack, r["price_inr"]) for r, pack in zip(matched, parsed) if pack and r.get("price_inr")]

    rows = []
    for row, pack in zip(matched, parsed):
        if row["delivery_status"] not in _DELIVERABLE:
            continue
        estimated = False
        if pack is None:
            pack = estimate_pack_size(row.get("price_inr"), known)
            estimated = pack is not None
        rows.append({
            **row,
            "brand": brand,
            "pack_size": pack,
            "pack_estimated": estimated,
            "unit_landed_cost": round(row["total_landed_cost"] / pack, 2) if pack else None,
        })
    return rows


def _best_listing(rows: List[dict]) -> Optional[dict]:
    """Cheapest per tablet among listings with a pack size (stated or estimated); otherwise cheapest total."""
    with_pack = [r for r in rows if r["pack_size"]]
    if with_pack:
        return min(with_pack, key=lambda r: (r["unit_landed_cost"], r["pack_estimated"]))
    return min(rows, key=lambda r: r["total_landed_cost"]) if rows else None


def compare_to_reference(row: dict, reference: dict) -> dict:
    """
    Savings of `row` vs `reference`: per tablet when both have a pack size, else total.
    estimated=True when either per-tablet figure rests on an estimated pack size.
    """
    if row["pack_size"] and reference["pack_size"]:
        basis, cost, ref_cost = "per_tablet", row["unit_landed_cost"], reference["unit_landed_cost"]
        estimated = bool(row.get("pack_estimated") or reference.get("pack_estimated"))
    else:
        basis, cost, ref_cost = "total", row["total_landed_cost"], reference["total_landed_cost"]
        estimated = False
    savings = round(ref_cost - cost, 2)
    return {
        "price_basis": basis,
        "savings": savings,
        "savings_pct": round(savings / ref_cost * 100, 1) if ref_cost else 0.0,
        "is_cheaper": savings > 0,
        "estimated": estimated,
    }


def _sort_key(row: dict):
    return row["unit_landed_cost"] if row["unit_landed_cost"] is not None else row["total_landed_cost"]


# ─────────────────────────────────────────────
# Assembly (searches run in pipeline.py)
# ─────────────────────────────────────────────

# A main search that finds fewer real listings of the medicine than this is kept for 1 h, not 24 h:
# Google sometimes answers "Stamlo 5 price" with other brands only, and a day-long cache would pin
# that. 1 h is also how long SerpApi replays an identical search from its own cache.
MIN_MAIN_LISTINGS = 3
THIN_RESULT_TTL = 3600


def thin_result_ttl(name: str):
    """ttl_for callback for the main search: THIN_RESULT_TTL when the result is thin, else None."""
    def ttl_for(raw: dict):
        real = [r for r in distill_shopping_results(raw)
                if title_matches_brand(r.get("medicine_name", ""), name, allows_other_forms(name))]
        return THIN_RESULT_TTL if len(real) < MIN_MAIN_LISTINGS else None
    return ttl_for


def ranked_listings(name: str, pincode, exact_only: bool = False, verbose: bool = False) -> List[dict]:
    """
    search → distill → delivery-inclusive ranking for one medicine name.
    The main search (exact_only=False) keeps a thin result for 1 h only; substitute searches
    (exact_only=True) are often thin for real (brand not sold online) and keep the full TTL.
    """
    from pharmawatch.search import search_prices
    ttl_for = None if exact_only else thin_result_ttl(name)
    raw = search_prices(name, verbose=verbose, exact_only=exact_only, ttl_for=ttl_for)
    return rank_by_landed_price(distill_shopping_results(raw), pincode)


def listing_key(row: dict) -> Tuple[str, str, float]:
    """Identity of one product listing across searches (the same offer shows up in several)."""
    return (row.get("platform", ""), " ".join(str(row.get("medicine_name", "")).lower().split()), row.get("price_inr"))


def pool_listings(*ranked_lists: List[dict]) -> List[dict]:
    """All listings from several searches, each distinct offer once (first occurrence wins)."""
    seen, pooled = set(), []
    for rows in ranked_lists:
        for row in rows:
            key = listing_key(row)
            if key not in seen:
                seen.add(key)
                pooled.append(row)
    return pooled


def allows_other_forms(query: str, entry: Optional[dict] = None) -> bool:
    """Keep syrup/injection/... titles only if the search or its composition is that form (e.g. insulin)."""
    text = f"{query} {entry['name']} {entry['active_ingredient']}" if entry else query
    return bool(set(_TOKEN_RE.findall(text.lower())) & _OTHER_FORMS)


def main_listings(rows: List[dict], name: str, pincode, allow_other_forms: bool = False) -> List[dict]:
    """
    Only the listings that really are `name` (Fix for 'Stamlo 5' returning Esta 5 / Stalopam 5 /
    Stamlo Bis), re-ranked by landed price. Empty if none are.
    """
    matched = [r for r in rows if title_matches_brand(r.get("medicine_name", ""), name, allow_other_forms)]
    return rank_by_landed_price(matched, pincode)


def assemble_alternatives(
    query: str,
    match: dict,
    main_rows: List[dict],
    pooled: List[dict],
) -> dict:
    """
    Compare the substitutes against the searched medicine. No I/O.
      match     : find_composition() result
      main_rows : main_listings() of the searched medicine — the reference price comes from these
      pooled    : pool_listings() of every search in this run (main + all substitutes); each
                  substitute is looked for in all of them, not only in its own search
    Returns:
      {
        "query", "composition" (name/active_ingredient/drug_class/brands),
        "suggested_alternatives": the ≤3 substitutes Gemini picked (all searched and priced),
        "matched_as": "brand" | "salt", "matched_brand",
        "matched_by": "exact" | "gemini", "match_reason",
        "reference":            searched brand's cheapest deliverable listing (None for salt searches
                                or when it isn't deliverable here),
        "cheaper_alternatives": best listing per brand that beats the reference, cheapest first,
                                with price_basis/savings/savings_pct/estimated,
        "other_alternatives":   best listing per brand that is not cheaper (or every brand when
                                there's no reference), cheapest first,
        "not_found":            brands with no deliverable listing at this PIN in any search,
      }
    Every listing row carries pack_size + pack_estimated (True = pack size inferred, not stated).
    """
    entry, matched_brand = match["entry"], match["matched_brand"]
    allow_other_forms = allows_other_forms(query, entry)

    reference = None
    if matched_brand:
        reference = _best_listing(_prepare(main_rows, matched_brand, allow_other_forms))

    cheaper, others, not_found = [], [], []
    for brand in match["alternatives"]:
        best = _best_listing(_prepare(pooled, brand, allow_other_forms))
        if best is None:
            not_found.append(brand)
            continue
        if reference is not None:
            best.update(compare_to_reference(best, reference))
        (cheaper if best.get("is_cheaper") else others).append(best)

    cheaper.sort(key=_sort_key)
    others.sort(key=_sort_key)

    return {
        "query": query,
        "composition": {k: entry[k] for k in ("name", "active_ingredient", "drug_class", "brands")},
        "suggested_alternatives": match["alternatives"],
        "matched_as": match["matched_as"],
        "matched_brand": matched_brand,
        "matched_by": match["matched_by"],
        "match_reason": match["reason"],
        "reference": reference,
        "cheaper_alternatives": cheaper,
        "other_alternatives": others,
        "not_found": not_found,
    }
