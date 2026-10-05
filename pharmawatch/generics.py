"""
generics.py — the searched medicine's listings and its cheaper same-composition brands.

Flow for a search like "Stamlo 5" at PIN 110001 (searches run in parallel in pipeline.py):
  1. medicines.resolve() finds what the search names in the Indian Medicine Dataset: a brand
     (Stamlo 5 → Amlodipine 5mg tablet), a salt (Gliclazide 80mg), or an ambiguous name that needs a
     strength first (paracetamol). Spelling is corrected against the dataset; when several fixes fit,
     Gemini picks one of the dataset's candidates and the pick is checked in code. Gemini never sees
     web data and never invents a medicine.
  2. Every brand with the same composition key (salts, strengths, form, release) is a substitute:
     116 brands for Gliclazide 80mg tablet, while Glizid-M (with metformin) is a different key.
  3. A brand search adds one search by salt ('Amlodipine 5mg'): Google answers it with the brands of
     that salt sold online. Every listing of every search in the run is checked against every brand
     of the composition, so brands nobody searched for count too. Titles must be that brand +
     strength: look-alike combinations (M / AT / Bis / '5/50mg') are rejected.
  4. Compare per-tablet landed price (delivery included) against the searched brand's cheapest
     deliverable listing. A pack size missing from a title is estimated from the brand's other
     listings and flagged (pack_estimated / estimated); with no usable pack size, total landed price
     is compared.
"""

import hashlib
import math
import re
import warnings
from collections import Counter
from typing import Dict, List, Optional, Tuple

from pharmawatch.comparator import rank_by_landed_price
from pharmawatch.distiller import distill_shopping_results

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
# What the search names (pharmawatch/medicines.py, from the Indian Medicine Dataset)
# ─────────────────────────────────────────────

MAX_SHOWN = 8             # best-per-brand rows returned per list


def find_composition(query: str, use_llm: bool = True, resolution: Optional[dict] = None) -> Optional[dict]:
    """
    The composition group the search belongs to, or None when the dataset doesn't know it.
      resolution : medicines.resolve(query), when the caller already has it
    Returns {"entry", "matched_as": "brand" | "salt", "matched_brand", "matched_by": "exact" | "fuzzy" |
             "gemini", "reason", "comp_key", "salt_query", "group",
             "alternatives": [] (the extra searches, filled by pick_candidates)}.
    An ambiguous search (no strength) never gets here: the pipeline asks the user first.
    """
    from pharmawatch import medicines

    res = resolution or medicines.resolve(query)
    if res["kind"] == "candidates":
        res = _choose_candidate(query, res["candidates"], use_llm)
    if res.get("kind") not in ("brand", "salt"):
        return None

    group = medicines.same_composition(res["comp_key"])
    if res["kind"] == "brand":
        reason = f"{res['brand']} is {res['label']}"
        if res.get("matched_by") in ("fuzzy", "gemini"):
            reason = f"Read '{query}' as {res['brand']} ({res['label']})"
    else:
        reason = f"{len(group)} brands sell {res['label']}"
    return {
        "entry": {"name": res["label"], "active_ingredient": res["salts"], "drug_class": "",
                  "brands": [g["brand"] for g in group[:12]], "brand_count": len(group)},
        "matched_as": res["kind"],
        "matched_brand": res.get("brand"),
        "manufacturer": res.get("manufacturer"),
        "matched_by": res.get("matched_by", "exact"),
        "reason": reason,
        "comp_key": res["comp_key"],
        "salt_query": medicines.salt_query(res),
        "form": res.get("form", ""),
        "generic_query": generic_query(medicines.salt_query(res), res["form"]),
        "strengths": res.get("strengths", ""),
        "group": group,
        "alternatives": [],
    }


def group_matcher(match: dict):
    """title → the group brand row it is a listing of (same brand and strength, combinations rejected), or None."""
    by_first: Dict[str, List[dict]] = {}
    for g in match["group"]:
        by_first.setdefault(g["first_token"], []).append(g)
    allow = allows_other_forms(match["entry"]["name"])

    def brand_of(title: str) -> Optional[dict]:
        hits = [g for t in dict.fromkeys(_tokens(title)) for g in by_first.get(t, ())
                if title_matches_brand(title, g["brand"], allow)]
        return max(hits, key=lambda g: len(g["brand_tokens"].split())) if hits else None
    return brand_of


# Makers whose generic ranges pharmacies discount hardest. On 1mg, Chemist180 and Medplus the
# "cheaper alternative" offered for Dolo 650, Stamlo 5 and Atorbest 10 was a Cipla brand each time
# (Paracip 650 ₹1.39/tab, Parafast 650 ₹1.52, Amlip 5 ₹1.35, Lipvas 10 ₹3.30) although those rank
# 449th/500, 243rd/281 and 557th/655 by list price: cheap only after the pharmacy's discount, so
# list prices can't find them. One search for the group's brand from these makers can: Google answers
# a brand search with ~10 same-salt brands, and "Paracip 650" found Paracip at ₹1.08/tab (Netmeds).
# Among the maker's brands the one with the largest family (most products under its name) is picked:
# thin lines such as Cipmol 650 surface less.
GENERIC_LINE_MAKERS = ("cipla ltd",)


def generic_line_brand(match: dict) -> Optional[str]:
    """The group's biggest brand family from GENERIC_LINE_MAKERS, never the searched brand."""
    searched = set(_tokens(match["matched_brand"] or ""))
    rows = [g for g in match["group"]
            if (g.get("manufacturer") or "").lower() in GENERIC_LINE_MAKERS
            and set(g["brand_tokens"].split()) != searched]
    if not rows:
        return None
    return min(rows, key=lambda g: (-(g.get("family_products") or 0), g["unit_mrp"] is None, g["unit_mrp"] or 0,
                                    g["brand"]))["brand"]


def generic_query(salt_query: str, form: str) -> str:
    """'Amlodipine 5mg' → 'Amlodipine 5mg tablet generic'. The word 'generic' steers Google Shopping to the
    discounted generics pharmacies push: 'Atorvastatin 10mg tablet generic' found Torvason 10 at ₹2.14/tab
    (Chemist180), 'Amlodipine 5mg tablet generic' Amodep 5 at ₹1.01; the plain salt found ₹2.47 and ₹1.15."""
    return f"{salt_query} tablet generic" if form == "tablet" else f"{salt_query} generic"


def pick_candidates(match: dict, found: List[dict]) -> List[str]:
    """
    The 2 extra searches after the main one. Any search in the same salt widens the pool: Google lists
    ~10 related brands of that salt, and every listing is checked against the whole group.
      1. the salt + 'tablet generic' (generic_query): the discounted generics pharmacies push
      2. the GENERIC_LINE_MAKERS brand with the largest family ('Paracip 650': Paracip at ₹1.08/tab);
         a salt search with no such brand gets the widest-range maker's brand instead
         ('Sitagliptin 50mg' → Istavel 50, 2 listings became 14)
    Picking brands by list price was tried first: for Gliclazide 80mg none of the 3 chosen brands
    appeared in their own results (their results added other gliclazide brands through pooling).
    """
    searches = [match["generic_query"]]
    # Chemist180 delivers free and discounts its own generics hardest; naming it surfaces brands no other
    # query returns (Thyrorich 50 ₹0.14/tab, Pantopraz 40 ₹0.66, Atorless 10 ₹2.73 vs the pharmacy's own
    # suggestions at ₹0.70, ₹2.25, ₹3.30). Single-salt only: for combinations it returned nothing.
    if "+" not in match["salt_query"]:
        searches.append(match["generic_query"] + " chemist180")
    # Google sometimes answers a short brand name with other brands only ("Pan 40 price": 24 listings,
    # none of Pan 40; "Atorbest 10 price": Atorbest 20 only). With the form word it finds them
    # ("Pan 40 tablet": 5 listings of Pan 40), so that search is added when the brand is missing.
    if match["matched_as"] == "brand" and match["matched_brand"]:
        allow = allows_other_forms(match["matched_brand"], match["entry"])
        if not any(title_matches_brand(r.get("medicine_name", ""), match["matched_brand"], allow) for r in found):
            form = (match.get("form") or "tablet").split()[-1]
            searches.insert(0, f"{match['matched_brand']} {form}")
    brand = generic_line_brand(match)
    if brand is None and match["matched_as"] == "salt":
        widest = max(match["group"], key=lambda g: (g.get("maker_products") or 0, -(g["unit_mrp"] or 1e9)), default=None)
        brand = widest["brand"] if widest else None
    if brand:
        searches.append(brand)
    return searches


# Spelling fixes with several possible answers: Gemini picks from the dataset's candidates only.
_DECISION_TTL = 30 * 86_400
_CHOICE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"choice": {"type": "INTEGER", "nullable": True}, "reason": {"type": "STRING"}},
    "required": ["choice", "reason"],
}
_PROMPT = """A user searched an Indian pharmacy site for "{query}". The spelling doesn't match any medicine
exactly. These are the closest medicines in our catalogue:

{candidates}

Which one did the user most likely mean? Answer with its number, or null if none is a plausible reading
of the search. reason: one short sentence."""


def _decision_version() -> str:
    """Changes when the medicine index or the prompt changes, so stale cached decisions are ignored."""
    from pharmawatch.medicines import INDEX_PATH
    stat = INDEX_PATH.stat()
    return hashlib.sha256(f"{stat.st_size}|{_PROMPT}".encode()).hexdigest()[:12]


def _decision_store():
    """Redis backend of the shared SerpApi cache, or None in passthrough mode."""
    from pharmawatch.search import _get_cache
    return _get_cache(verbose=False).backend


def _choose_candidate(query: str, candidates: List[tuple], use_llm: bool) -> dict:
    """Several spelling fixes fit ('dollo' → Dolo / Dollar ...). Gemini picks one; the pick is checked."""
    options = [res for _, res in candidates]
    if use_llm:
        choice = _gemini_choice(query, options)
        if choice is not None:
            return {**options[choice], "matched_by": "gemini"}
    return {**options[0], "matched_by": "fuzzy"}   # closest spelling first (difflib order)


def _gemini_choice(query: str, options: List[dict]) -> Optional[int]:
    from pharmawatch.gemini import GeminiError, generate_json

    listing = "\n".join(f"{i + 1}. {o.get('brand') or o['label']} ({o['label']})" for i, o in enumerate(options))
    normalized = " ".join(sorted(set(_tokens(query))))
    cache_key = "gemini-pick:" + hashlib.sha256(f"{_decision_version()}|{normalized}|{listing}".encode()).hexdigest()[:16]
    store = _decision_store()
    decision = store.get_by_key(cache_key) if store else None
    if decision is None:
        try:
            decision = generate_json(_PROMPT.format(query=query, candidates=listing), _CHOICE_SCHEMA)
        except GeminiError as e:
            warnings.warn(f"Gemini unavailable, using the closest spelling — {e}")
            return None
        if store:
            store.set(cache_key, decision, [], _DECISION_TTL, f"gemini-pick {normalized}")
    choice = decision.get("choice")
    return choice - 1 if isinstance(choice, int) and 1 <= choice <= len(options) else None


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


def _prepare(ranked: List[dict], brand: str, allow_other_forms: bool,
             strengths: str = "", default_pack: Optional[int] = None) -> List[dict]:
    """
    Deliverable listings of this brand, each with pack_size, pack_estimated and unit_landed_cost.
    Pack sizes missing from a title are estimated from every listing of the brand (deliverable or not),
    then from the dataset's usual pack for the brand (default_pack); both are flagged as estimated.
    strengths: the composition's doses, never read as a pack size ('Glycigon 80 Tablet 10's' → 10).
    """
    matched = [r for r in ranked if title_matches_brand(r.get("medicine_name", ""), brand, allow_other_forms)]
    parsed = [parse_pack_size(r["medicine_name"], f"{brand} {strengths}") for r in matched]
    known = [(pack, r["price_inr"]) for r, pack in zip(matched, parsed) if pack and r.get("price_inr")]

    rows = []
    for row, pack in zip(matched, parsed):
        if row["delivery_status"] not in _DELIVERABLE:
            continue
        estimated = False
        if pack is None:
            pack = estimate_pack_size(row.get("price_inr"), known) or default_pack
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


def listing_filter(name: str, match: Optional[dict] = None):
    """
    title → True when the listing is the searched medicine:
      brand search  → that brand + strength ('Stamlo 5', never 'Stamlo Bis 5')
      salt search   → any brand of the same composition ('Gliclazide 80mg' → Glizid 80, Diamicron 80 ...)
      unknown       → the search itself as a brand name (today's rule)
    """
    if match and match["matched_as"] == "salt":
        brand_of = group_matcher(match)
        return lambda title: brand_of(title) is not None
    brand = (match or {}).get("matched_brand") or name
    allow = allows_other_forms(name, match["entry"] if match else None)
    return lambda title: title_matches_brand(title, brand, allow)


def thin_result_ttl(name: str):
    """ttl_for callback for the main search: THIN_RESULT_TTL when the result is thin, else None."""
    def ttl_for(raw: dict):
        try:
            match = find_composition(name, use_llm=False)
        except Exception:
            match = None
        keep = listing_filter(name, match)
        real = [r for r in distill_shopping_results(raw) if keep(r.get("medicine_name", ""))]
        return THIN_RESULT_TTL if len(real) < MIN_MAIN_LISTINGS else None
    return ttl_for


def ranked_listings(name: str, pincode, exact_only: bool = False, verbose: bool = False,
                    main: Optional[bool] = None) -> List[dict]:
    """
    search → distill → delivery-inclusive ranking for one medicine name.
    exact_only: no semantic reuse. Brand names always (a similar brand with the same dose is another
                product: 'Atorbest 10' must never get 'Atorva 10' results).
    main: the user's own search (default: not exact_only). It keeps a thin result for 1 h only; extra
          searches are often thin for real (brand not sold online) and keep the full TTL.
    """
    from pharmawatch.search import search_prices
    is_main = (not exact_only) if main is None else main
    ttl_for = thin_result_ttl(name) if is_main else None
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


def main_listings(rows: List[dict], name: str, pincode, allow_other_forms: bool = False,
                  match: Optional[dict] = None) -> List[dict]:
    """
    Only the listings that really are the searched medicine (Fix for 'Stamlo 5' returning Esta 5 /
    Stalopam 5 / Stamlo Bis; for a salt search, any brand of that exact composition), re-ranked by
    landed price. Each row gets its brand's manufacturer when the dataset knows it. Empty if none match.
    """
    if match:
        keep = listing_filter(name, match)
    else:
        keep = lambda title: title_matches_brand(title, name, allow_other_forms)  # noqa: E731
    matched = [r for r in rows if keep(r.get("medicine_name", ""))]
    if match:
        brand_of = group_matcher(match)
        for r in matched:
            g = brand_of(r.get("medicine_name", ""))
            maker = g["manufacturer"] if g else match.get("manufacturer")
            if maker:
                r["manufacturer"] = maker
            if g:
                r["brand"] = g["brand"]
    return rank_by_landed_price(matched, pincode)


WIDELY_STOCKED = 3   # distinct pharmacies selling a brand here


def assemble_alternatives(
    query: str,
    match: dict,
    main_rows: List[dict],
    pooled: List[dict],
) -> dict:
    """
    Compare every brand of the same composition found in this run against the searched medicine. No I/O.
      match     : find_composition() result, with "alternatives" = the brands searched live
      main_rows : main_listings() of the searched medicine — the reference price comes from these
      pooled    : pool_listings() of every search in this run (main + substitutes); every listing is
                  checked against every brand of the composition, so brands nobody searched for count too
    Returns:
      {
        "query", "composition" (name/active_ingredient/drug_class/brands/brand_count),
        "suggested_alternatives": the extra searches made this run (the salt search for a brand),
        "matched_as": "brand" | "salt", "matched_brand",
        "matched_by": "exact" | "fuzzy" | "gemini", "match_reason",
        "reference":            searched brand's cheapest deliverable listing (None for salt searches
                                or when it isn't deliverable here),
        "cheaper_alternatives": best listing per brand that beats the reference, cheapest first,
                                with price_basis/savings/savings_pct/estimated,
        "other_alternatives":   best listing per brand that is not cheaper (every brand for a salt
                                search), cheapest first,
        "not_found":            brands searched by name with no deliverable listing at this PIN,
      }
    Rows carry pack_size, pack_estimated, manufacturer and widely_stocked (≥ 3 pharmacies here).
    """
    entry, matched_brand = match["entry"], match["matched_brand"]
    allow_other_forms = allows_other_forms(query, entry)

    strengths = match.get("strengths", "")
    searched = set(_tokens(matched_brand or ""))
    reference = None
    if matched_brand:
        own = next((g for g in match["group"] if set(g["brand_tokens"].split()) == searched), None)
        reference = _best_listing(_prepare(main_rows, matched_brand, allow_other_forms, strengths,
                                           own["pack"] if own else None))

    brand_of = group_matcher(match)
    by_brand: Dict[str, Tuple[dict, List[dict]]] = {}
    for row in pooled:
        g = brand_of(row.get("medicine_name", ""))
        if g is not None:
            by_brand.setdefault(g["brand_tokens"], (g, []))[1].append(row)

    cheaper, others = [], []
    for tokens, (g, rows) in by_brand.items():
        if matched_brand and set(tokens.split()) == searched:
            continue
        prepared = _prepare(rows, g["brand"], allow_other_forms, strengths, g["pack"])
        best = _best_listing(prepared)
        if best is None:
            continue
        best["manufacturer"] = g["manufacturer"]
        best["widely_stocked"] = len({r["platform"] for r in prepared}) >= WIDELY_STOCKED
        if reference is not None:
            best.update(compare_to_reference(best, reference))
        (cheaper if best.get("is_cheaper") else others).append(best)

    cheaper.sort(key=_sort_key)
    others.sort(key=_sort_key)
    found = {" ".join(sorted(set(_tokens(r["brand"])))) for r in cheaper + others}
    not_found = [b for b in match["alternatives"]
                 if b != match.get("salt_query") and " ".join(sorted(set(_tokens(b)))) not in found]

    return {
        "query": query,
        "composition": {k: entry[k] for k in ("name", "active_ingredient", "drug_class", "brands", "brand_count")},
        "suggested_alternatives": match["alternatives"],
        "matched_as": match["matched_as"],
        "matched_brand": matched_brand,
        "matched_by": match["matched_by"],
        "match_reason": match["reason"],
        "reference": reference,
        "cheaper_alternatives": cheaper[:MAX_SHOWN],
        "other_alternatives": others[:MAX_SHOWN],
        "not_found": not_found,
    }
