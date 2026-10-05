"""The API's result dicts (api.main.collect_search / collect_prescription / cache_lab) → output models."""

from typing import Optional

from .models import (
    BasketItem,
    Composition,
    Generic,
    LabOutput,
    Listing,
    MedicineView,
    NearQuery,
    NeedsStrength,
    Order,
    Plan,
    PrescriptionOutput,
    RunSummary,
    SearchOutput,
    StrengthOption,
)

PLAN_TITLES = {
    "cheapest_with_swaps": "Cheapest overall (same-salt swaps, any pharmacies)",
    "one_pharmacy": "One pharmacy (same-salt swaps, one order)",
    "as_prescribed": "Exactly as prescribed",
}


# ── Links ────────────────────────────────────────────────────────────────────

def link_info(row: dict) -> tuple[Optional[str], Optional[str]]:
    """(url, link_type). The distiller's placeholder direct_link equals the search link: not a product page."""
    direct, search, google = row.get("direct_link") or "", row.get("search_link") or "", row.get("google_link") or ""
    if direct and direct not in (search, google):
        return direct, "product_page"
    if search and "google." not in search:
        return search, "store_search"
    url = google or search
    return (url, "google_shopping") if url else (None, None)


def _linked(row: dict) -> dict:
    url, kind = link_info(row)
    return {"listing_id": row.get("link_id"), "link": url, "link_type": kind}


# ── Pieces ───────────────────────────────────────────────────────────────────

def listing(x: dict) -> Listing:
    return Listing(rank=x.get("rank"), pharmacy=x.get("platform") or "?", product=x.get("medicine_name") or "",
                   shelf_price_inr=x.get("price_inr"), delivery_fee_inr=x.get("delivery_fee"),
                   platform_fee_inr=x.get("platform_fee"), you_pay_inr=x.get("total_landed_cost"),
                   delivery=x.get("delivery_label"), delivery_status=x.get("delivery_status"),
                   arrives=x.get("estimated_days"), is_cheapest=bool(x.get("is_cheapest")), **_linked(x))


def generic(a: Optional[dict]) -> Optional[Generic]:
    if not a:
        return None
    return Generic(brand=a.get("brand"), manufacturer=a.get("manufacturer"), pharmacy=a.get("platform"),
                   product=a.get("medicine_name"), you_pay_inr=a.get("total_landed_cost"),
                   per_tablet_inr=a.get("unit_landed_cost"), pack_size=a.get("pack_size"),
                   pack_estimated=bool(a.get("pack_estimated")), saving_inr=a.get("savings"),
                   saving_pct=a.get("savings_pct"), saving_basis=a.get("price_basis"),
                   saving_estimated=bool(a.get("estimated")), widely_stocked=a.get("widely_stocked"), **_linked(a))


def run_summary(summary: Optional[dict]) -> Optional[RunSummary]:
    if not summary:
        return None
    return RunSummary(serpapi_lookups=summary["calls"], credits_spent=summary["credits_spent"],
                      from_cache=summary["credits_saved"], exact_hits=summary["exact_hits"],
                      semantic_hits=summary["semantic_hits"], seconds=round(summary["total_ms"] / 1000, 2))


def needs_strength(choose: dict) -> NeedsStrength:
    return NeedsStrength(medicine=choose["query"],
                         options=[StrengthOption(label=o["label"], query=o["query"]) for o in choose["options"]])


def brands_only(names: Optional[list], searched: Optional[str]) -> list[str]:
    """Not-found names minus our own search strings ('X generic', a retry of the searched brand)."""
    out = []
    for n in names or []:
        low = str(n).lower()
        if "generic" in low or (searched and low.startswith(searched.lower())):
            continue
        out.append(str(n))
    return out


def _error(r: dict) -> Optional[str]:
    return f"{r['error']['code']}: {r['error']['message']}" if r.get("error") else None


# ── search_medicine ──────────────────────────────────────────────────────────

def search_output(r: dict) -> SearchOutput:
    if r.get("choose"):
        return SearchOutput(query=r["query"], medicine=r["query"], pincode=r["pincode"],
                            needs_strength=needs_strength(r["choose"]), run=run_summary(r["summary"]))
    alts = r["alternatives"] or {}
    comp = alts.get("composition") or {}
    corrected = alts.get("matched_by") in ("fuzzy", "gemini")
    medicine = (alts.get("matched_brand") or comp.get("name") or r["query"]) if corrected else r["query"]
    listings = [listing(x) for x in r["listings"] or []]
    return SearchOutput(
        query=r["query"], medicine=medicine, spelling_corrected=corrected, pincode=r["pincode"],
        composition=Composition(name=comp.get("name"), active_ingredient=comp.get("active_ingredient"),
                                brands_with_same_composition=comp.get("brand_count")) if comp else None,
        cheapest=next((x for x in listings if x.is_cheapest), None),
        listings=listings,
        reference=generic(alts.get("reference")),
        cheaper_generics=[generic(a) for a in alts.get("cheaper_alternatives") or []],
        other_generics=[generic(a) for a in alts.get("other_alternatives") or []],
        not_sold_here=brands_only(alts.get("not_found"), alts.get("matched_brand") or r["query"]),
        run=run_summary(r["summary"]),
        error=_error(r),
    )


# ── plan_prescription ────────────────────────────────────────────────────────

def basket_item(o: dict, names: list[str]) -> BasketItem:
    line = o.get("line", 0)
    return BasketItem(medicine=names[line] if line < len(names) else f"line {line + 1}", buy=o["brand"],
                      is_swap=not o.get("prescribed", True), product=o.get("medicine_name"),
                      manufacturer=o.get("manufacturer"), packs=o["packs"], pack_size=o.get("pack_size"),
                      pack_estimated=bool(o.get("pack_estimated")), unit=o.get("unit") or "tablet",
                      cost_inr=o["item_cost"], per_unit_inr=o.get("per_tablet"), **_linked(o))


def plan(kind: str, p: Optional[dict], names: list[str]) -> Optional[Plan]:
    if not p:
        return None
    orders = [Order(pharmacy=s["platform"], items=[basket_item(o, names) for o in s["lines"]], subtotal_inr=s["subtotal"],
                    delivery_fee_inr=s["fee"], total_inr=s["total"], free_delivery=bool(s["free_delivery"]),
                    delivery=s.get("delivery_label")) for s in p["stores"]]
    return Plan(plan=kind, title=PLAN_TITLES[kind], total_inr=p["total"], medicines_inr=p["items_total"],
                delivery_inr=p["fees_total"], orders=orders)


def prescription_output(r: dict) -> PrescriptionOutput:
    names = [it["query"] for it in r["items"]]
    needs = [needs_strength(ln["choose"]) for _, ln in sorted(r["lines"].items(), key=lambda kv: int(kv[0]))
             if ln.get("status") == "choose" and ln.get("choose")]
    out = PrescriptionOutput(pincode=r["pincode"], needs_strength=needs, run=run_summary(r["summary"]), error=_error(r))
    b = r.get("basket")
    if not b:
        return out
    plans = [plan("cheapest_with_swaps", b["with_swaps"]["best"], names),
             plan("one_pharmacy", b["with_swaps"]["single_store"], names),
             plan("as_prescribed", b["as_prescribed"]["best"], names)]
    out.plans = [p for p in plans if p]
    out.saving_vs_prescribed_inr = b.get("saving")
    out.saving_covers = [names[i] for i in b.get("saving_lines") or [] if i < len(names)]
    out.per_medicine = [
        MedicineView(medicine=names[p["line"]] if p["line"] < len(names) else p["query"],
                     units_needed=p.get("tablets"), units_how=p.get("tablets_how"),
                     cheapest_prescribed=basket_item(p["cheapest_prescribed"], names) if p.get("cheapest_prescribed") else None,
                     cheapest_any=basket_item(p["cheapest_any"], names) if p.get("cheapest_any") else None)
        for p in b.get("per_line") or []
    ]
    out.not_sold_here = [names[i] for i in b.get("unavailable") or [] if i < len(names)]
    out.combinations_priced = (b.get("stats") or {}).get("combinations")
    return out


# ── cache_lab ────────────────────────────────────────────────────────────────

def lab_output(lab: dict) -> LabOutput:
    return LabOutput(input=lab["input"], decision=lab["decision"], reason=lab["reason"],
                     credits_if_searched=lab["credits"], normalized_query=lab["normalized_query"],
                     threshold=lab["threshold"], compared_against=lab["compared_against"],
                     timings_ms=lab["timings_ms"],
                     nearest=[NearQuery(cached_query=c["query_text"].split(" | ")[0], similarity=c["similarity"],
                                        above_threshold=c["above_threshold"], same_params=c["same_params"],
                                        dosage_guard_blocks=c["dosage_guard_blocks"]) for c in lab["nearest"]])
