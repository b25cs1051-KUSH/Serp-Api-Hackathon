"""
basket.py — the cheapest way to buy a whole prescription, delivery included. No I/O.

Each pharmacy charges delivery on its own order total: 1mg is free from ₹100, Apollo from ₹199,
Netmeds from ₹500, Chemist180 always. Buying each medicine where it is cheapest alone can therefore
cost more than putting two of them in one order, so the basket is optimised as a whole:

    lines   = [{"query": "Dolo 650", "tablets": 30}, {"query": "Stamlo 5", "tablets": None}, ...]
    offers  = build_offers(...) per line              → every deliverable way to cover its tablets
    result  = optimise(offers_per_line, pincode)      → best split, best single pharmacy, per line

Tablets needed: the count typed by the user, else one pack of the prescribed medicine's cheapest
offer (the smallest purchase). A substitute with another pack size is bought in as many packs as
needed to cover the same tablets.

Two answers are computed:
  as_prescribed : only the prescribed brand (any brand of the composition for a salt search)
  with_swaps    : any brand with the same salts, strengths, form and release (same composition key)

The search is exact over the offers kept: every line keeps its cheapest offer per pharmacy, the
best MAX_STORES_PER_LINE of those (fewer when there are many lines, so at most MAX_COMBINATIONS
assignments are tried), and every assignment of lines to pharmacies is priced with the real
delivery rules on each pharmacy's subtotal.
"""

import itertools
import math
import time
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from pharmawatch.delivery_cost import calculate_delivery_cost
from pharmawatch.generics import _best_listing, _prepare, _tokens, allows_other_forms, group_matcher

MAX_STORES_PER_LINE = 8
MAX_COMBINATIONS = 200_000
_DELIVERABLE = ("free", "charged")


# ─────────────────────────────────────────────
# Offers: every way to buy one line
# ─────────────────────────────────────────────

def _prepared_by_brand(pooled: List[dict], match: Optional[dict], query: str) -> Dict[str, List[dict]]:
    """Deliverable listings with pack sizes, grouped by brand (same composition only)."""
    if match is None:  # medicine the index doesn't know: only its own name
        rows = _prepare(pooled, query, allows_other_forms(query))
        return {query: rows} if rows else {}
    brand_of = group_matcher(match)
    allow = allows_other_forms(query, match["entry"])
    grouped: Dict[str, Tuple[dict, List[dict]]] = {}
    for row in pooled:
        g = brand_of(row.get("medicine_name", ""))
        if g is not None:
            grouped.setdefault(g["brand"], (g, []))[1].append(row)
    out = {}
    for brand, (g, rows) in grouped.items():
        prepared = _prepare(rows, brand, allow, match.get("strengths", ""), g["pack"])
        for r in prepared:
            r["manufacturer"] = g.get("manufacturer")
        if prepared:
            out[brand] = prepared
    return out


def _is_prescribed(brand: str, match: Optional[dict], query: str) -> bool:
    if match is None or match["matched_as"] == "salt":
        return True
    return set(_tokens(brand)) == set(_tokens(match["matched_brand"]))


def tablets_needed(line: dict, by_brand: Dict[str, List[dict]], match: Optional[dict]) -> Tuple[Optional[int], str]:
    """(tablets, how): the typed count, else one pack of the prescribed medicine's cheapest offer."""
    if line.get("tablets"):
        return int(line["tablets"]), "typed"
    prescribed = [r for b, rows in by_brand.items() if _is_prescribed(b, match, line["query"]) for r in rows]
    best = _best_listing(prescribed) or _best_listing([r for rows in by_brand.values() for r in rows])
    if best is None or not best.get("pack_size"):
        return None, "unknown"
    return int(best["pack_size"]), "one pack"


def build_offers(line: dict, pooled: List[dict], match: Optional[dict]) -> dict:
    """
    {"tablets", "tablets_how", "offers": [...]} — one offer per brand × pharmacy (its cheapest way to
    cover the tablets). Offer: brand, platform, packs, pack_size, pack_estimated, price_inr (per pack),
    item_cost (packs × price), per_tablet, prescribed, medicine_name, manufacturer, links.
    """
    by_brand = _prepared_by_brand(pooled, match, line["query"])
    tablets, how = tablets_needed(line, by_brand, match)
    offers = []
    if tablets:
        for brand, rows in by_brand.items():
            best_per_store: Dict[str, dict] = {}
            for r in rows:
                if not r.get("pack_size") or r.get("delivery_status") not in _DELIVERABLE:
                    continue
                packs = math.ceil(tablets / r["pack_size"])
                cost = round(packs * r["price_inr"], 2)
                cur = best_per_store.get(r["platform"])
                if cur is None or (cost, r["pack_estimated"]) < (cur["item_cost"], cur["pack_estimated"]):
                    best_per_store[r["platform"]] = {
                        "brand": brand,
                        "platform": r["platform"],
                        "packs": packs,
                        "pack_size": r["pack_size"],
                        "pack_estimated": bool(r["pack_estimated"]),
                        "price_inr": r["price_inr"],
                        "item_cost": cost,
                        "per_tablet": round(cost / (packs * r["pack_size"]), 2),
                        "prescribed": _is_prescribed(brand, match, line["query"]),
                        "medicine_name": r.get("medicine_name", ""),
                        "manufacturer": r.get("manufacturer"),
                        "direct_link": r.get("direct_link") or "",
                        "search_link": r.get("search_link") or "",
                        "google_link": r.get("google_link") or "",
                        "page_token": r.get("page_token") or "",
                    }
            offers.extend(best_per_store.values())
    offers.sort(key=lambda o: (o["item_cost"], o["pack_estimated"], o["platform"]))
    return {"tablets": tablets, "tablets_how": how, "offers": offers}


# ─────────────────────────────────────────────
# Optimisation
# ─────────────────────────────────────────────

def _fee_function(pincode):
    @lru_cache(maxsize=4096)
    def fee(platform: str, subtotal: float) -> Optional[Tuple[float, str, bool]]:
        q = calculate_delivery_cost(platform, subtotal, pincode)
        if q["delivery_status"] not in _DELIVERABLE or q["delivery_fee"] is None:
            return None
        return round(q["delivery_fee"] + (q["platform_fee"] or 0.0), 2), q["delivery_label"], q["is_free_delivery"]
    return fee


def _choices(offers: List[dict], keep: int) -> List[dict]:
    """Cheapest offer per pharmacy, the `keep` cheapest pharmacies."""
    best: Dict[str, dict] = {}
    for o in offers:
        if o["platform"] not in best or o["item_cost"] < best[o["platform"]]["item_cost"]:
            best[o["platform"]] = o
    return sorted(best.values(), key=lambda o: o["item_cost"])[:keep]


def _price(assignment: Tuple[dict, ...], fee) -> Optional[Tuple[float, Dict[str, float]]]:
    subtotals: Dict[str, float] = {}
    for o in assignment:
        subtotals[o["platform"]] = subtotals.get(o["platform"], 0.0) + o["item_cost"]
    total = 0.0
    for platform, sub in subtotals.items():
        f = fee(platform, round(sub, 2))
        if f is None:
            return None
        total += sub + f[0]
    return round(total, 2), subtotals


def _search(per_line: List[List[dict]], fee) -> Tuple[Optional[Tuple[dict, ...]], int]:
    """Cheapest assignment of one offer per line; (best, combinations tried)."""
    lines = len(per_line)
    keep = MAX_STORES_PER_LINE
    while keep > 1 and math.prod(min(keep, len(c)) for c in per_line) > MAX_COMBINATIONS:
        keep -= 1
    choices = [c[:keep] for c in per_line]
    best, best_total, tried = None, math.inf, 0
    for assignment in itertools.product(*choices):
        tried += 1
        priced = _price(assignment, fee)
        if priced is not None and priced[0] < best_total:
            best, best_total = assignment, priced[0]
    return (best if lines else None), tried


def _describe(assignment: Tuple[dict, ...], line_ids: List[int], fee) -> dict:
    stores: Dict[str, dict] = {}
    for i, o in zip(line_ids, assignment):
        s = stores.setdefault(o["platform"], {"platform": o["platform"], "lines": [], "subtotal": 0.0})
        s["lines"].append({**o, "line": i})
        s["subtotal"] = round(s["subtotal"] + o["item_cost"], 2)
    for s in stores.values():
        f, label, free = fee(s["platform"], s["subtotal"])
        s.update(fee=f, delivery_label=label, free_delivery=free, total=round(s["subtotal"] + f, 2))
    out = sorted(stores.values(), key=lambda s: -s["total"])
    return {
        "total": round(sum(s["total"] for s in out), 2),
        "items_total": round(sum(s["subtotal"] for s in out), 2),
        "fees_total": round(sum(s["fee"] for s in out), 2),
        "stores": out,
    }


def _single_store(per_line: List[List[dict]], line_ids: List[int], fee) -> Optional[dict]:
    """Cheapest pharmacy that has every line."""
    common = set.intersection(*[{o["platform"] for o in c} for c in per_line]) if per_line else set()
    best = None
    for platform in common:
        assignment = tuple(min((o for o in c if o["platform"] == platform), key=lambda o: o["item_cost"])
                           for c in per_line)
        priced = _price(assignment, fee)
        if priced is not None and (best is None or priced[0] < best[0]):
            best = (priced[0], assignment)
    return _describe(best[1], line_ids, fee) if best else None


def optimise(lines: List[dict], pincode) -> dict:
    """
    lines: [{"query", "tablets", "tablets_how", "offers": [...]}] (build_offers output + query).
    Returns {
      "with_swaps":   {"best": plan | None, "single_store": plan | None},
      "as_prescribed":{"best": plan | None, "single_store": plan | None},
      "saving": as_prescribed best total − with_swaps best total (or None),
      "per_line": [{"line", "query", "tablets", "tablets_how", "cheapest_prescribed", "cheapest_any"}],
      "unavailable": [line indexes with no deliverable offer],
      "stats": {"combinations": int, "ms": float},
    }
    plan = {"total", "items_total", "fees_total", "stores": [{"platform", "lines": [offer + line],
            "subtotal", "fee", "delivery_label", "free_delivery", "total"}]}
    """
    t0 = time.perf_counter()
    fee = _fee_function(pincode)
    per_line, unavailable = [], []
    for i, line in enumerate(lines):
        deliverable = [o for o in line["offers"] if fee(o["platform"], round(o["item_cost"], 2)) is not None]
        solo = sorted(deliverable, key=lambda o: o["item_cost"] + fee(o["platform"], round(o["item_cost"], 2))[0])
        prescribed = [o for o in solo if o["prescribed"]]
        per_line.append({"line": i, "query": line["query"], "tablets": line.get("tablets"),
                         "tablets_how": line.get("tablets_how"),
                         "cheapest_prescribed": prescribed[0] if prescribed else None,
                         "cheapest_any": solo[0] if solo else None,
                         "_offers": deliverable})
        if not deliverable:
            unavailable.append(i)

    tried = 0
    result = {}
    for mode, keep_offer in (("with_swaps", lambda o: True), ("as_prescribed", lambda o: o["prescribed"])):
        rows = [(p["line"], _choices([o for o in p["_offers"] if keep_offer(o)], len(p["_offers"])))
                for p in per_line if p["line"] not in unavailable]
        rows = [(i, c) for i, c in rows if c]
        ids, choices = [i for i, _ in rows], [c for _, c in rows]
        if not choices:
            result[mode] = {"best": None, "single_store": None, "lines": []}
            continue
        best, n = _search(choices, fee)
        tried += n
        result[mode] = {"best": _describe(best, ids, fee) if best else None,
                        "single_store": _single_store(choices, ids, fee),
                        "lines": ids}

    ws, ap = result["with_swaps"]["best"], result["as_prescribed"]["best"]
    comparable = ws and ap and result["with_swaps"]["lines"] == result["as_prescribed"]["lines"]
    for p in per_line:
        p.pop("_offers")
    return {
        **result,
        "saving": round(ap["total"] - ws["total"], 2) if comparable else None,
        "per_line": per_line,
        "unavailable": unavailable,
        "stats": {"combinations": tried, "ms": round((time.perf_counter() - t0) * 1000, 1)},
    }
