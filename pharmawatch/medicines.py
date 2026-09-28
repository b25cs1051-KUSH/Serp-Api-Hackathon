"""
medicines.py — what a medicine is: brand ↔ composition lookups from the Indian Medicine Dataset.

drug_db/medicines.sqlite.gz is built by scripts/build_medicine_index.py from
https://github.com/junioralive/Indian-Medicine-Dataset (MIT). Each product has a composition key —
salts with strengths, form and release type — and products sharing a key are interchangeable brands:

    resolve("Stamlo 5")         → brand   Stamlo 5, Amlodipine 5mg tablet
    resolve("Gliclazide 80mg")  → salt    Gliclazide 80mg tablet
    resolve("paracetamol")      → ambiguous: 500mg / 650mg / 1000mg tablet, syrup ...
    resolve("dollo 650")        → brand   Dolo 650 (spelling corrected, matched_by="fuzzy")
    same_composition(key)       → every brand with that key, cheapest list price per unit first

Prices here are list prices (MRP). They only rank which brands to search; live prices come from SerpApi.
"""

import difflib
import gzip
import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pharmawatch.generics import _tokens

INDEX_PATH = Path(__file__).parent / "drug_db" / "medicines.sqlite.gz"

# ─────────────────────────────────────────────
# Normalisation (shared by the index builder and the lookups)
# ─────────────────────────────────────────────

_SALT_ALIASES = {
    "paracetamol/acetaminophen": "paracetamol",
    "acetaminophen": "paracetamol",
    "amoxycillin": "amoxicillin",
    "metformin hydrochloride": "metformin",
}
# Modified release; XR / XL are the same idea as ER.
_RELEASE = {"sr": "sr", "er": "er", "xr": "er", "xl": "er", "pr": "pr", "cr": "cr", "mr": "mr"}
_UNIT_WORDS = {"ml", "gm", "mg", "g", "l", "kg", "mcg"}
_FORM_CUT_RE = re.compile(
    r"\s+(?:tablets?|capsules?|dry syrup|syrup|injection|suspension|oral|drops?|eye|ear|nasal|cream|gel|"
    r"ointment|lotion|solution|infusion|powder|kit|soap|shampoo|spray|inhaler|rotacaps?|respules?|sachets?|"
    r"granules|expectorant|linctus|emulsion|paste|mouthwash|lozenges?|patch|softgel|vaccine|serum|liquid|"
    r"drink|cap|tab|caps|tabs)\b.*$",
    re.I,
)
_COMPONENT_RE = re.compile(r"^(.*)\((.*?)\)\s*$")
_PACK_RE = re.compile(r"of\s+(\d+)\s+(?:soft\s+gelatin\s+)?(?:tablet|capsule)", re.I)
_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)")


def _salt(name: str) -> str:
    n = " ".join(re.sub(r"\(.*?\)", " ", name).lower().split())
    return _SALT_ALIASES.get(n, n)


def _strength(s: str) -> str:
    s = s.replace(" ", "").lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:gm|g)", s)
    return f"{float(m.group(1)) * 1000:g}mg" if m else s


def _form_release(pack_label: str, name: str) -> Tuple[str, str]:
    """'strip of 10 tablet sr' → ('tablet', 'sr'); 'bottle of 60 ml syrup' → ('syrup', '')."""
    suffix = re.sub(r"^.*?\d[\d.]*\s*", "", pack_label.lower()).strip() or pack_label.lower()
    words = [w for w in re.findall(r"[a-z]+", suffix) if w not in _UNIT_WORDS]
    release = next((_RELEASE[w] for w in words if w in _RELEASE), "")
    if not release:
        release = next((_RELEASE[w] for w in re.findall(r"[a-z]+", name.lower()) if w in _RELEASE), "")
    form = [w for w in words if w not in _RELEASE]
    form = ["tablet" if w == "tablets" else "capsule" if w == "capsules" else w for w in form]
    if form[:2] == ["soft", "gelatin"]:
        form = form[2:]
    return " ".join(form) or "unit", release


def composition_key(comp1: str, comp2: str, pack_label: str, name: str):
    """(key, label, salts, salt_words, strengths, form, release), or None when there is no usable salt."""
    parts = []
    for comp in (comp1, comp2):
        comp = (comp or "").strip()
        m = _COMPONENT_RE.match(comp)
        if not m:
            continue
        salt, strength = _salt(m.group(1)), _strength(m.group(2))
        if salt:
            parts.append((salt, strength))
    if not parts:
        return None
    parts.sort()
    form, release = _form_release(pack_label, name)
    key = "+".join(f"{s}:{st}" for s, st in parts) + f"|{form}|{release}"
    salts = " + ".join(f"{s.title()} {st}" for s, st in parts)
    label = f"{salts} {form}" + (f" {release.upper()}" if release else "")
    salt_words = " ".join(sorted({w for s, _ in parts for w in _tokens(s) if w.isalpha()}))
    strengths = " ".join(m.group(1) for _, st in parts if (m := _NUM_RE.match(st)))
    return key, label, salts, salt_words, strengths, form, release


def brand_name(name: str) -> str:
    """'Glizid-M OD 60 Tablet SR' → 'Glizid-M OD 60'; 'Dolo 650 Tablet' → 'Dolo 650'."""
    return " ".join(_FORM_CUT_RE.sub("", " " + name.strip()).split())


def name_tokens(brand: str) -> List[str]:
    return _tokens(brand)


def pack_count(pack_label: str) -> Optional[int]:
    m = _PACK_RE.search(pack_label or "")
    return int(m.group(1)) if m and 0 < int(m.group(1)) <= 1000 else None


def _num(t: str) -> str:
    return f"{float(t):g}"


# ─────────────────────────────────────────────
# Index access
# ─────────────────────────────────────────────

_SETUP = """
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_tokens);
CREATE INDEX IF NOT EXISTS idx_products_first ON products(first_token);
CREATE INDEX IF NOT EXISTS idx_products_comp ON products(comp_id);
CREATE INDEX IF NOT EXISTS idx_comp_salts ON compositions(salt_words);
CREATE TABLE IF NOT EXISTS maker_size AS
    SELECT manufacturer_id, COUNT(*) AS n FROM products GROUP BY manufacturer_id;
CREATE INDEX IF NOT EXISTS idx_maker_size ON maker_size(manufacturer_id);
CREATE TABLE IF NOT EXISTS brand_family AS
    SELECT first_token, COUNT(*) AS n FROM products GROUP BY first_token;
CREATE INDEX IF NOT EXISTS idx_brand_family ON brand_family(first_token);
CREATE VIEW IF NOT EXISTS product_view AS
    SELECT p.brand, p.brand_tokens, p.first_token, c.comp_key, p.mrp, p.pack,
           CASE WHEN p.mrp > 0 AND p.pack > 0 THEN round(p.mrp / p.pack, 4) END AS unit_mrp,
           m.name AS manufacturer, ms.n AS maker_products, bf.n AS family_products
    FROM products p JOIN compositions c ON c.id = p.comp_id
    LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
    LEFT JOIN maker_size ms ON ms.manufacturer_id = p.manufacturer_id
    LEFT JOIN brand_family bf ON bf.first_token = p.first_token;
"""

_local = threading.local()
_unpack_lock = threading.Lock()


def _db_path() -> str:
    """The index, unpacked once to the temp dir (the app directory is read-only in Docker)."""
    stat = INDEX_PATH.stat()
    setup = hashlib.sha256(_SETUP.encode()).hexdigest()[:8]
    target = os.path.join(tempfile.gettempdir(), f"pharmawatch-medicines-{setup}-{stat.st_size}-{int(stat.st_mtime)}.sqlite")
    with _unpack_lock:
        if not os.path.exists(target):
            partial = target + f".{os.getpid()}.part"
            with gzip.open(INDEX_PATH, "rb") as src, open(partial, "wb") as dst:
                shutil.copyfileobj(src, dst)
            db = sqlite3.connect(partial)
            db.executescript(_SETUP)
            db.close()
            os.replace(partial, target)
    return target


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def _q(sql: str, *args) -> List[sqlite3.Row]:
    return _conn().execute(sql, args).fetchall()


@lru_cache(maxsize=1)
def _vocabulary() -> Tuple[List[str], List[str]]:
    """Brand first words and salt words, for spelling correction."""
    firsts = [r[0] for r in _q("SELECT DISTINCT first_token FROM products") if r[0].isalpha() and len(r[0]) > 2]
    salts = sorted({w for r in _q("SELECT DISTINCT salt_words FROM compositions") for w in r[0].split()})
    return firsts, salts


# ─────────────────────────────────────────────
# Lookups
# ─────────────────────────────────────────────

_ORAL_SOLID_FIRST = ("tablet", "capsule")


def _comp_info(comp_key: str) -> Optional[dict]:
    rows = _q("SELECT * FROM compositions WHERE comp_key = ?", comp_key)
    return dict(rows[0]) if rows else None


def _form_rank(form: str) -> int:
    return 0 if form == "tablet" else 1 if form == "capsule" else 2


def _brand_result(rows: List[sqlite3.Row], matched_by: str) -> dict:
    """The most common composition among products named exactly like the search."""
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["comp_key"]] = counts.get(r["comp_key"], 0) + 1
    comp_key = max(counts, key=lambda k: (counts[k], -_form_rank(k.split("|")[1])))
    product = next(r for r in rows if r["comp_key"] == comp_key)
    return {"kind": "brand", "comp_key": comp_key, "brand": product["brand"], "manufacturer": product["manufacturer"],
            "matched_by": matched_by, **_comp_info(comp_key)}


@lru_cache(maxsize=1)
def _form_vocab() -> frozenset:
    """Every word used in a form or release ('oral', 'suspension', 'dt', 'sr' ...)."""
    words = {w for r in _q("SELECT DISTINCT form FROM compositions") for w in r[0].split()}
    return frozenset(words | set(_RELEASE))


def _option(info: dict) -> dict:
    """A search that resolves to exactly this composition: 'Paracetamol 250mg syrup', 'Metformin 500mg SR'."""
    salts = re.sub(r"(\d+(?:\.\d+)?[a-z%]*)/[\w.]+", r"\1", info["salts"])
    form = "" if info["form"] == "tablet" else f" {info['form']}"
    release = f" {info['release'].upper()}" if info["release"] else ""
    return {"label": info["label"], "query": f"{salts}{form}{release}", "comp_key": info["comp_key"]}


def salt_query(info: dict) -> str:
    """The search for a composition by its salt: 'Amlodipine 5mg', 'Metformin 500mg SR'."""
    return _option(info)["query"]


def _strength_in_composition(row, toks: List[str]) -> bool:
    """The brand's name words are all in the search and the search's other words are its strengths."""
    brand = set(row["brand_tokens"].split())
    extra = set(toks) - brand
    if not brand < set(toks) or any(t.isalpha() for t in extra):
        return False
    strengths = {_num(n) for n in (_comp_info(row["comp_key"]) or {}).get("strengths", "").split()}
    return {_num(t) for t in extra} <= strengths


def _has_strength_variants(first: str, toks: List[str]) -> bool:
    """'Dolo' → Dolo 650, Dolo 500 ... exist: the search needs a strength."""
    return any(set(toks) < set(r["brand_tokens"].split())
               and all(not t.isalpha() for t in set(r["brand_tokens"].split()) - set(toks))
               for r in _q("SELECT brand_tokens FROM products WHERE first_token = ?", first))


def resolve(query: str, _fuzzy: bool = True) -> dict:
    """
    What the search names:
      {"kind": "brand", "brand", "comp_key", "label", "salts", ...}   a product ('Stamlo 5')
      {"kind": "salt", "comp_key", "label", "salts", ...}             a composition ('Gliclazide 80mg')
      {"kind": "ambiguous", "options": [{label, query, comp_key}]}    needs a strength or a brand variant
      {"kind": "none"}
    matched_by: "exact" or "fuzzy" (spelling corrected against the dataset's names).
    """
    toks = _tokens(query)
    if not toks:
        return {"kind": "none"}
    key = " ".join(sorted(set(toks)))

    words = {t for t in toks if t.isalpha()}
    nums = {_num(t) for t in toks if not t.isalpha()}
    release = next((_RELEASE[w] for w in words if w in _RELEASE), None)
    form_words = (words & _form_vocab()) - set(_RELEASE)
    salt_words = words - _form_vocab()
    comps = [dict(r) for r in _q("SELECT * FROM compositions WHERE salt_words = ?", " ".join(sorted(salt_words)))] if salt_words else []
    first = toks[0]

    # 1. A product named exactly like the search. A salt name ('paracetamol') is a salt search even
    #    when some product is sold under that name, and a brand named without its strength ('Dolo')
    #    is ambiguous when it comes in several strengths.
    rows = [] if comps else _q("SELECT * FROM product_view WHERE brand_tokens = ?", key)
    if rows and (nums or not _has_strength_variants(first, toks)):
        return _brand_result(rows, "exact")

    # 2. A salt name with or without strength / release / form words.
    if comps:
        if release is not None:
            comps = [c for c in comps if c["release"] == release] or comps
        if form_words:
            comps = [c for c in comps if form_words <= set(c["form"].split())] or comps
        matching = [c for c in comps if nums and {_num(n) for n in c["strengths"].split()} == nums]
        if matching:
            if release is None:
                matching = [c for c in matching if c["release"] == ""] or matching
            best = min(matching, key=lambda c: (_form_rank(c["form"]), -c["products"]))
            return {"kind": "salt", "brand": None, "manufacturer": None, "matched_by": "exact", **best}
        usable = [c for c in comps if c["strengths"]]
        options = sorted(usable or comps, key=lambda c: (_form_rank(c["form"]), -c["products"]))[:8]
        return {"kind": "ambiguous", "options": [_option(c) for c in options],
                "reason": "strength not given" if not nums else "no product with that strength"}

    # 3. A brand named without its strength ('Dolo' → Dolo 650 / Dolo 500 ...), or a brand whose name
    #    has no strength while the search does ('Telma H 40' → Telma-H, telmisartan 40mg + HCTZ).
    #    Extra words may only be numbers: 'Telma 40 H' never becomes 'Telma-AM H 40'.
    candidates = _q("SELECT * FROM product_view WHERE first_token = ?", first)
    rows = [r for r in candidates if set(toks) <= set(r["brand_tokens"].split())
            and all(not t.isalpha() for t in set(r["brand_tokens"].split()) - set(toks))]
    if not rows and nums:
        rows = [r for r in candidates if _strength_in_composition(r, toks)]
    if rows:
        brands: Dict[str, List[sqlite3.Row]] = {}
        for r in rows:
            brands.setdefault(r["brand_tokens"], []).append(r)
        if len(brands) == 1:
            return _brand_result(rows, "exact")
        ranked = sorted(brands.values(), key=lambda rs: (_form_rank(rs[0]["comp_key"].split("|")[1]), -len(rs), rs[0]["brand"]))
        return {"kind": "ambiguous", "reason": "several products share this name",
                "options": [{"label": rs[0]["brand"], "query": rs[0]["brand"], "comp_key": rs[0]["comp_key"]} for rs in ranked[:8]]}

    # 4. Spelling: correct the first word against brand and salt names, then try again.
    if _fuzzy and first.isalpha():
        firsts, salts = _vocabulary()
        seen, found = set(), []
        for cand in difflib.get_close_matches(first, salts + firsts, n=4, cutoff=0.8):
            fixed = " ".join([cand, *toks[1:]])
            res = resolve(fixed, _fuzzy=False)
            if res["kind"] != "none" and res.get("comp_key", fixed) not in seen:
                seen.add(res.get("comp_key", fixed))
                found.append((cand, res))
        if len(found) == 1:
            return {**found[0][1], "matched_by": "fuzzy", "corrected": found[0][0]}
        if found:
            return {"kind": "candidates", "candidates": found}
    return {"kind": "none"}


def same_composition(comp_key: str) -> List[dict]:
    """Every brand with this composition, one row per brand, cheapest list price per unit first."""
    best: Dict[str, dict] = {}
    for r in _q("SELECT brand, brand_tokens, first_token, mrp, pack, unit_mrp, manufacturer, maker_products, family_products FROM product_view WHERE comp_key = ?", comp_key):
        row = dict(r)
        cur = best.get(row["brand_tokens"])
        price = row["unit_mrp"] if row["unit_mrp"] is not None else row["mrp"]
        cur_price = None if cur is None else (cur["unit_mrp"] if cur["unit_mrp"] is not None else cur["mrp"])
        if cur is None or (price is not None and (cur_price is None or price < cur_price)):
            best[row["brand_tokens"]] = row
    return sorted(best.values(), key=lambda r: (r["unit_mrp"] is None, r["unit_mrp"] or 0, r["brand"]))
