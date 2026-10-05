"""
mcp_server.py — PharmaWatch as an MCP server (stdio), for Claude Desktop, MCP Inspector or any MCP client.

Tools (thin wrappers over api/main.py, the same code path as the web app's HTTP API, so validation,
the concurrency limit, the search deadline, the daily credit budget and credit accounting are shared):

  search_medicine(query, pincode, resolve_links=False)   delivered prices + cheaper same-salt brands
  plan_prescription(medicines, pincode, resolve_links=False)
                                                         the cheapest way to buy a whole prescription:
                                                         3 plans, orders per pharmacy, per-medicine view
  get_buy_link(listing_id)                               a listing's own pharmacy product page, resolved
                                                         on demand (= the web app's /api/link/{id})
  cache_lab(query)                                       what the semantic cache would do, 0 credits
  cache_stats()                                          Redis contents + hit/credit counters

Every tool returns readable Markdown (or JSON text with response_format="json") AND typed
structuredContent that matches the tool's published outputSchema. Every listing and basket item
carries a listing_id; pass it to get_buy_link for the product page.

Prompts: compare_medicine, plan_my_prescription.

The protocol owns stdout: main() serves it on a private copy and points fd 1 and sys.stdout at
stderr, so the cache's console prints and library warnings go to the client's server log.

Run from anywhere:
    python mcp_server.py
    npx @modelcontextprotocol/inspector python mcp_server.py
"""

import copy
import io
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")  # MCP clients start servers from any working directory

import anyio  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from mcp.server.mcpserver import Context, MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import CallToolResult, TextContent, ToolAnnotations  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import api.main as api  # noqa: E402

log = logging.getLogger("pharmawatch.mcp")

MAX_ROWS = 10  # listings shown in Markdown; structuredContent always has every listing
ResponseFormat = Annotated[
    Literal["markdown", "json"],
    Field(description="Text form of the result: 'markdown' (default, compact and readable) or 'json'. "
                      "Typed structuredContent is returned either way."),
]
LinkType = Literal["product_page", "store_search", "google_shopping"]
CAUTION = "Same salt, strength and form. Ask a doctor or pharmacist before switching brands."


@asynccontextmanager
async def lifespan(server: MCPServer):
    # Load the embedding model off the request path, exactly like the HTTP API.
    threading.Thread(target=api._warm, daemon=True, name="warm-up").start()
    yield


mcp = MCPServer(
    name="pharmawatch",
    title="PharmaWatch",
    version="0.2.0",
    instructions=(
        "PharmaWatch finds where an Indian medicine is cheapest once delivery to the buyer's PIN code is "
        "included, and which brands with the same salt, strength and form cost less. Prices are live Google "
        "Shopping data via SerpApi, cached in Redis for 24 h.\n"
        "Workflow: search_medicine for one medicine, plan_prescription for several (it optimises the whole "
        "basket across pharmacies, delivery fees included). Show the user the delivered price ('you pay'), "
        "not the shelf price. Every listing has a listing_id: when the user wants to buy one, call "
        "get_buy_link(listing_id) for that pharmacy's own product page.\n"
        "If a medicine name has no strength (e.g. 'paracetamol'), the tools return the options instead of "
        "searching (0 credits): ask the user which one is on the prescription.\n"
        "Credits: a new medicine costs about 4 SerpApi credits (main search plus up to 3 same-salt "
        "searches); repeat or similar searches are free from cache. get_buy_link costs 1 credit the first "
        "time per listing, then 0 for 24 h. cache_lab predicts the main lookup for free. Keep resolve_links "
        "false and use get_buy_link for the listing the user actually picks.\n"
        "Always tell the user that swaps have the same salt, strength and form, and that they should check "
        "with a doctor or pharmacist before switching. This is price information, not medical advice."
    ),
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# Output models (published as each tool's outputSchema)
# ─────────────────────────────────────────────

class RunSummary(BaseModel):
    serpapi_lookups: int = Field(description="SerpApi requests made, cached or not")
    credits_spent: int = Field(description="Lookups that called SerpApi (cache misses)")
    from_cache: int
    exact_hits: int
    semantic_hits: int
    seconds: float


class Listing(BaseModel):
    rank: Optional[int] = None
    pharmacy: str
    product: str = Field(description="Title as the pharmacy lists it")
    shelf_price_inr: Optional[float] = None
    delivery_fee_inr: Optional[float] = Field(None, description="Null when the pharmacy doesn't publish it")
    platform_fee_inr: Optional[float] = None
    you_pay_inr: Optional[float] = Field(None, description="Shelf price + delivery + platform fee to this PIN")
    delivery: Optional[str] = Field(None, description="One-line delivery explanation")
    delivery_status: Optional[str] = None
    arrives: Optional[str] = None
    is_cheapest: bool = False
    listing_id: Optional[str] = Field(None, description="Pass to get_buy_link for the product page")
    link: Optional[str] = None
    link_type: Optional[LinkType] = None


class Generic(BaseModel):
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    pharmacy: Optional[str] = None
    product: Optional[str] = None
    you_pay_inr: Optional[float] = None
    per_tablet_inr: Optional[float] = Field(None, description="Delivered cost per tablet (delivery included)")
    pack_size: Optional[int] = None
    pack_estimated: bool = False
    saving_inr: Optional[float] = None
    saving_pct: Optional[float] = None
    saving_basis: Optional[str] = Field(None, description="'per_tablet' or 'total'")
    saving_estimated: bool = Field(False, description="True when the saving depends on an estimated pack size")
    widely_stocked: Optional[bool] = None
    listing_id: Optional[str] = None
    link: Optional[str] = None
    link_type: Optional[LinkType] = None


class StrengthOption(BaseModel):
    label: str
    query: str = Field(description="Call the tool again with this as the medicine name")


class NeedsStrength(BaseModel):
    medicine: str
    options: list[StrengthOption]


class Composition(BaseModel):
    name: Optional[str] = None
    active_ingredient: Optional[str] = None
    brands_with_same_composition: Optional[int] = None


class SearchOutput(BaseModel):
    query: str = Field(description="What the user typed")
    medicine: str = Field(description="The medicine actually searched (spelling corrected if needed)")
    spelling_corrected: bool = False
    pincode: str
    needs_strength: Optional[NeedsStrength] = Field(None, description="Set when nothing was searched yet")
    composition: Optional[Composition] = None
    cheapest: Optional[Listing] = Field(None, description="Cheapest listing that can be delivered")
    listings: list[Listing] = Field(default_factory=list, description="Ranked by delivered price")
    reference: Optional[Generic] = Field(None, description="The searched brand's best per-tablet offer")
    cheaper_generics: list[Generic] = Field(default_factory=list)
    other_generics: list[Generic] = Field(default_factory=list)
    not_sold_here: list[str] = Field(default_factory=list, description="Same-salt brands searched but not deliverable")
    caution: str = CAUTION
    run: Optional[RunSummary] = None
    error: Optional[str] = Field(None, description="Set when the search finished only partly")


class BasketItem(BaseModel):
    medicine: str = Field(description="The prescription line this item covers")
    buy: str = Field(description="Brand to buy")
    is_swap: bool = Field(description="True when it replaces the prescribed brand with the same salt")
    product: Optional[str] = None
    manufacturer: Optional[str] = None
    packs: int
    pack_size: Optional[int] = None
    pack_estimated: bool = False
    unit: str = Field("tablet", description="'tablet', or 'item' for syrups, creams and similar")
    cost_inr: float = Field(description="Packs × shelf price, before delivery")
    per_unit_inr: Optional[float] = Field(None, description="Per tablet (or item), before delivery")
    listing_id: Optional[str] = None
    link: Optional[str] = None
    link_type: Optional[LinkType] = None


class Order(BaseModel):
    pharmacy: str
    items: list[BasketItem]
    subtotal_inr: float
    delivery_fee_inr: float
    total_inr: float
    free_delivery: bool
    delivery: Optional[str] = None


class Plan(BaseModel):
    plan: Literal["cheapest_with_swaps", "one_pharmacy", "as_prescribed"]
    title: str
    total_inr: float
    medicines_inr: float
    delivery_inr: float
    orders: list[Order]


class MedicineView(BaseModel):
    medicine: str
    units_needed: Optional[int] = None
    units_how: Optional[str] = Field(None, description="'typed' or 'one pack'")
    cheapest_prescribed: Optional[BasketItem] = None
    cheapest_any: Optional[BasketItem] = None


class PrescriptionOutput(BaseModel):
    pincode: str
    plans: list[Plan] = Field(default_factory=list,
                              description="Cheapest with swaps, best single pharmacy, exactly as prescribed")
    saving_vs_prescribed_inr: Optional[float] = None
    saving_covers: list[str] = Field(default_factory=list, description="Medicines the saving is computed on")
    per_medicine: list[MedicineView] = Field(default_factory=list)
    needs_strength: list[NeedsStrength] = Field(default_factory=list, description="Lines left out until chosen")
    not_sold_here: list[str] = Field(default_factory=list)
    combinations_priced: Optional[int] = None
    caution: str = CAUTION
    run: Optional[RunSummary] = None
    error: Optional[str] = None


class BuyLinkOutput(BaseModel):
    listing_id: str
    pharmacy: Optional[str] = None
    product: Optional[str] = None
    url: str
    is_product_page: bool = Field(description="False when only the pharmacy's search page could be found")
    credits_spent: int
    seconds: float


class NearQuery(BaseModel):
    cached_query: str
    similarity: float
    above_threshold: bool
    same_params: bool
    dosage_guard_blocks: bool


class LabOutput(BaseModel):
    input: str
    decision: Literal["exact_hit", "semantic_hit", "api_call"]
    reason: str
    credits_if_searched: int
    normalized_query: str
    threshold: float
    compared_against: int
    timings_ms: dict[str, float]
    nearest: list[NearQuery]


class StatsOutput(BaseModel):
    redis_ok: bool
    embedding_model: str
    similarity_threshold: float
    serpapi_key_configured: bool
    gemini_key_configured: bool
    cached_entries: dict[str, int]
    cached_bytes: int
    session: dict[str, Any] = Field(description="Counters for this server process since it started")


# ─────────────────────────────────────────────
# Conversions from the API's result dicts
# ─────────────────────────────────────────────

def _link_info(row: dict) -> tuple[Optional[str], Optional[str]]:
    """(url, link_type). The distiller's placeholder direct_link equals the search link: not a product page."""
    direct, search, google = row.get("direct_link") or "", row.get("search_link") or "", row.get("google_link") or ""
    if direct and direct not in (search, google):
        return direct, "product_page"
    if search and "google." not in search:
        return search, "store_search"
    url = google or search
    return (url, "google_shopping") if url else (None, None)


def _linked(row: dict) -> dict:
    url, kind = _link_info(row)
    return {"listing_id": row.get("link_id"), "link": url, "link_type": kind}


def _listing(x: dict) -> Listing:
    return Listing(rank=x.get("rank"), pharmacy=x.get("platform") or "?", product=x.get("medicine_name") or "",
                   shelf_price_inr=x.get("price_inr"), delivery_fee_inr=x.get("delivery_fee"),
                   platform_fee_inr=x.get("platform_fee"), you_pay_inr=x.get("total_landed_cost"),
                   delivery=x.get("delivery_label"), delivery_status=x.get("delivery_status"),
                   arrives=x.get("estimated_days"), is_cheapest=bool(x.get("is_cheapest")), **_linked(x))


def _generic(a: Optional[dict]) -> Optional[Generic]:
    if not a:
        return None
    return Generic(brand=a.get("brand"), manufacturer=a.get("manufacturer"), pharmacy=a.get("platform"),
                   product=a.get("medicine_name"), you_pay_inr=a.get("total_landed_cost"),
                   per_tablet_inr=a.get("unit_landed_cost"), pack_size=a.get("pack_size"),
                   pack_estimated=bool(a.get("pack_estimated")), saving_inr=a.get("savings"),
                   saving_pct=a.get("savings_pct"), saving_basis=a.get("price_basis"),
                   saving_estimated=bool(a.get("estimated")), widely_stocked=a.get("widely_stocked"), **_linked(a))


def _run(summary: Optional[dict]) -> Optional[RunSummary]:
    if not summary:
        return None
    return RunSummary(serpapi_lookups=summary["calls"], credits_spent=summary["credits_spent"],
                      from_cache=summary["credits_saved"], exact_hits=summary["exact_hits"],
                      semantic_hits=summary["semantic_hits"], seconds=round(summary["total_ms"] / 1000, 2))


def _needs(choose: dict) -> NeedsStrength:
    return NeedsStrength(medicine=choose["query"],
                         options=[StrengthOption(label=o["label"], query=o["query"]) for o in choose["options"]])


def _brands_only(names: list, searched: Optional[str]) -> list[str]:
    """Not-found names minus our own search strings ('X generic', a retry of the searched brand)."""
    out = []
    for n in names or []:
        low = str(n).lower()
        if "generic" in low or (searched and low.startswith(searched.lower())):
            continue
        out.append(str(n))
    return out


def _search_output(r: dict) -> SearchOutput:
    if r.get("choose"):
        return SearchOutput(query=r["query"], medicine=r["query"], pincode=r["pincode"],
                            needs_strength=_needs(r["choose"]), run=_run(r["summary"]))
    alts = r["alternatives"] or {}
    comp = alts.get("composition") or {}
    corrected = alts.get("matched_by") in ("fuzzy", "gemini")
    medicine = (alts.get("matched_brand") or comp.get("name") or r["query"]) if corrected else r["query"]
    listings = [_listing(x) for x in r["listings"] or []]
    return SearchOutput(
        query=r["query"], medicine=medicine, spelling_corrected=corrected, pincode=r["pincode"],
        composition=Composition(name=comp.get("name"), active_ingredient=comp.get("active_ingredient"),
                                brands_with_same_composition=comp.get("brand_count")) if comp else None,
        cheapest=next((x for x in listings if x.is_cheapest), None),
        listings=listings,
        reference=_generic(alts.get("reference")),
        cheaper_generics=[_generic(a) for a in alts.get("cheaper_alternatives") or []],
        other_generics=[_generic(a) for a in alts.get("other_alternatives") or []],
        not_sold_here=_brands_only(alts.get("not_found"), alts.get("matched_brand") or r["query"]),
        run=_run(r["summary"]),
        error=f"{r['error']['code']}: {r['error']['message']}" if r.get("error") else None,
    )


def _item(o: dict, names: list[str]) -> BasketItem:
    line = o.get("line", 0)
    return BasketItem(medicine=names[line] if line < len(names) else f"line {line + 1}", buy=o["brand"],
                      is_swap=not o.get("prescribed", True), product=o.get("medicine_name"),
                      manufacturer=o.get("manufacturer"), packs=o["packs"], pack_size=o.get("pack_size"),
                      pack_estimated=bool(o.get("pack_estimated")), unit=o.get("unit") or "tablet",
                      cost_inr=o["item_cost"], per_unit_inr=o.get("per_tablet"), **_linked(o))


_PLAN_TITLES = {"cheapest_with_swaps": "Cheapest overall (same-salt swaps, any pharmacies)",
                "one_pharmacy": "One pharmacy (same-salt swaps, one order)",
                "as_prescribed": "Exactly as prescribed"}


def _plan(kind: str, p: Optional[dict], names: list[str]) -> Optional[Plan]:
    if not p:
        return None
    orders = [Order(pharmacy=s["platform"], items=[_item(o, names) for o in s["lines"]], subtotal_inr=s["subtotal"],
                    delivery_fee_inr=s["fee"], total_inr=s["total"], free_delivery=bool(s["free_delivery"]),
                    delivery=s.get("delivery_label")) for s in p["stores"]]
    return Plan(plan=kind, title=_PLAN_TITLES[kind], total_inr=p["total"], medicines_inr=p["items_total"],
                delivery_inr=p["fees_total"], orders=orders)


def _prescription_output(r: dict) -> PrescriptionOutput:
    names = [it["query"] for it in r["items"]]
    needs = [_needs(ln["choose"]) for _, ln in sorted(r["lines"].items(), key=lambda kv: int(kv[0]))
             if ln.get("status") == "choose" and ln.get("choose")]
    out = PrescriptionOutput(pincode=r["pincode"], needs_strength=needs, run=_run(r["summary"]),
                             error=f"{r['error']['code']}: {r['error']['message']}" if r.get("error") else None)
    b = r.get("basket")
    if not b:
        return out
    plans = [_plan("cheapest_with_swaps", b["with_swaps"]["best"], names),
             _plan("one_pharmacy", b["with_swaps"]["single_store"], names),
             _plan("as_prescribed", b["as_prescribed"]["best"], names)]
    out.plans = [p for p in plans if p]
    out.saving_vs_prescribed_inr = b.get("saving")
    out.saving_covers = [names[i] for i in b.get("saving_lines") or [] if i < len(names)]
    out.per_medicine = [MedicineView(medicine=names[p["line"]] if p["line"] < len(names) else p["query"],
                                     units_needed=p.get("tablets"), units_how=p.get("tablets_how"),
                                     cheapest_prescribed=_item(p["cheapest_prescribed"], names) if p.get("cheapest_prescribed") else None,
                                     cheapest_any=_item(p["cheapest_any"], names) if p.get("cheapest_any") else None)
                        for p in b.get("per_line") or []]
    out.not_sold_here = [names[i] for i in b.get("unavailable") or [] if i < len(names)]
    out.combinations_priced = (b.get("stats") or {}).get("combinations")
    return out


# ─────────────────────────────────────────────
# Markdown
# ─────────────────────────────────────────────

def _inr(value) -> str:
    return "—" if value is None else f"₹{value:,.2f}"


def _cell(text) -> str:
    return str(text or "—").replace("|", "\\|").replace("\n", " ")


def _buy_cell(x) -> str:
    """Product page as a link; otherwise the store search link and the id for get_buy_link."""
    if x.link_type == "product_page":
        return f"[product page]({x.link})"
    parts = []
    if x.link_type == "store_search":
        parts.append(f"[store search]({x.link})")
    if x.listing_id:
        parts.append(f"id `{x.listing_id}`")
    return " · ".join(parts) or "—"


def _pack(g: Generic) -> str:
    if not g.pack_size:
        return "—"
    return f"~{g.pack_size} (est.)" if g.pack_estimated else str(g.pack_size)


def _run_line(run: Optional[RunSummary]) -> str:
    if not run:
        return "No run summary."
    return (f"{run.serpapi_lookups} SerpApi lookups · {run.credits_spent} credit{'' if run.credits_spent == 1 else 's'} "
            f"spent · {run.from_cache} served from cache ({run.exact_hits} exact, {run.semantic_hits} semantic) · "
            f"{run.seconds:.1f} s")


_LINK_NOTE = ("Buy: `product page` opens the pharmacy's own page. For an `id`, call get_buy_link with it to get "
              "that pharmacy's product page (1 SerpApi credit the first time, then cached for 24 h).")


def _needs_markdown(n: NeedsStrength, tool: str) -> list[str]:
    out = [f"## Which {n.medicine}?", "",
           "It comes in more than one strength or form, so nothing was searched yet (0 credits). "
           f"Ask the user which one is on their prescription, then call {tool} again with it:", ""]
    return out + [f"- {o.label}: `{o.query}`" for o in n.options]


def _search_markdown(s: SearchOutput) -> str:
    if s.needs_strength:
        return "\n".join(_needs_markdown(s.needs_strength, "search_medicine"))
    out = [f"## {s.medicine}: delivered prices to PIN {s.pincode}", ""]
    if s.spelling_corrected:
        out += [f"_Read \"{s.query}\" as **{s.medicine}** (spelling corrected). Confirm with the user if unsure._", ""]
    if s.error:
        code, _, message = s.error.partition(": ")
        out += [f"> **Search incomplete ({code}):** {message}", ""]
    if s.listings:
        if s.cheapest:
            out += [f"Cheapest delivered: **{_inr(s.cheapest.you_pay_inr)}** at {s.cheapest.pharmacy} "
                    f"({s.cheapest.delivery or s.cheapest.delivery_status}).", ""]
        out += ["| # | Pharmacy | Product | Shelf price | Delivery | You pay | Arrives | Buy |",
                "|---|---|---|---|---|---|---|---|"]
        for i, x in enumerate(s.listings[:MAX_ROWS], 1):
            out.append(f"| {x.rank or i} | {_cell(x.pharmacy)} | {_cell(x.product)} | {_inr(x.shelf_price_inr)} | "
                       f"{_cell(x.delivery)} | {_inr(x.you_pay_inr)} | {_cell(x.arrives)} | {_buy_cell(x)} |")
        if len(s.listings) > MAX_ROWS:
            out.append(f"\n{len(s.listings) - MAX_ROWS} more listings in structuredContent (or response_format='json').")
    else:
        out.append("No listings found for this medicine.")

    out.append("")
    comp = s.composition
    if not comp:
        out.append("### Same-salt brands\nNot in the 246,000-medicine index, so no substitutes were compared.")
    else:
        out.append(f"### Same-salt brands: {comp.name or comp.active_ingredient}")
        if s.reference:
            unit = f", {_inr(s.reference.per_tablet_inr)}/tablet delivered" if s.reference.per_tablet_inr is not None else ""
            out.append(f"Reference: {_cell(s.reference.product)} at {s.reference.pharmacy}, "
                       f"{_inr(s.reference.you_pay_inr)}{unit}.")
        rows = s.cheaper_generics or (s.other_generics if not s.reference else [])
        if rows:
            saving_col = bool(s.cheaper_generics)
            out += ["", "| Brand | Maker | Pharmacy | You pay | Per tablet | Pack |" + (" Saving |" if saving_col else "") + " Buy |",
                    "|---|---|---|---|---|---|" + ("---|" if saving_col else "") + "---|"]
            for g in rows:
                saving = ""
                if saving_col:
                    approx = "≈" if g.saving_estimated else ""
                    basis = "/tablet" if g.saving_basis == "per_tablet" else ""
                    saving = (f" {approx}{g.saving_pct}% ({_inr(g.saving_inr)}{basis}) |"
                              if g.saving_pct is not None else " — |")
                out.append(f"| {_cell(g.brand)} | {_cell(g.manufacturer)} | {_cell(g.pharmacy)} | {_inr(g.you_pay_inr)} | "
                           f"{_inr(g.per_tablet_inr)} | {_pack(g)} |{saving} {_buy_cell(g)} |")
            out.append("\nPer tablet includes delivery. ~ = pack size estimated, ≈ = saving depends on it. " + CAUTION)
        else:
            out.append("No cheaper same-salt brand found online right now.")
        if s.not_sold_here:
            out.append(f"Not deliverable here right now: {', '.join(s.not_sold_here)}.")
    out += ["", _LINK_NOTE, "", "### Run", _run_line(s.run)]
    return "\n".join(out)


def _plan_markdown(p: PrescriptionOutput) -> str:
    out = [f"## Prescription: cheapest way to buy it, delivered to PIN {p.pincode}", ""]
    if p.error:
        code, _, message = p.error.partition(": ")
        out += [f"> **Incomplete ({code}):** {message}", ""]
    for n in p.needs_strength:
        opts = ", ".join(f"`{o.query}`" for o in n.options[:6])
        out += [f"**Which {n.medicine}?** Left out until the user picks one (0 credits): {opts}", ""]
    if not p.plans:
        return "\n".join(out + ["No basket could be built.", "", "### Run", _run_line(p.run)])

    best = p.plans[0]
    out.append(f"**{best.title}: {_inr(best.total_inr)}** ({_inr(best.medicines_inr)} medicines + "
               f"{_inr(best.delivery_inr)} delivery), {len(best.orders)} order{'s' if len(best.orders) > 1 else ''}: "
               f"{' + '.join(o.pharmacy for o in best.orders)}.")
    if p.saving_vs_prescribed_inr:
        out.append(f"That is {_inr(p.saving_vs_prescribed_inr)} less than the prescribed brands "
                   f"(compared on {len(p.saving_covers)} medicine{'s' if len(p.saving_covers) != 1 else ''} sold online).")
    out += ["", "| Order at | Medicine | Buy | Packs | Cost | Per unit | Link |", "|---|---|---|---|---|---|---|"]
    for o in best.orders:
        for it in o.items:
            buy = it.buy + (" (same-salt swap)" if it.is_swap else "")
            pack = f"{it.packs} × {'~' if it.pack_estimated else ''}{it.pack_size or '?'}"
            out.append(f"| {_cell(o.pharmacy)} | {_cell(it.medicine)} | {_cell(buy)} | {pack} | {_inr(it.cost_inr)} | "
                       f"{_inr(it.per_unit_inr)} | {_buy_cell(it)} |")
    out.append("")
    out += [f"- {o.pharmacy}: {_inr(o.subtotal_inr)} + {_inr(o.delivery_fee_inr)} delivery = {_inr(o.total_inr)}"
            for o in best.orders]
    others = [pl for pl in p.plans[1:]]
    if others:
        out += ["", "Other ways to buy it:"]
        for pl in others:
            diff = pl.total_inr - best.total_inr
            out.append(f"- {pl.title}: {_inr(pl.total_inr)} ({' + '.join(o.pharmacy for o in pl.orders)})"
                       + (f", {_inr(diff)} more" if diff > 0.005 else ""))
    if p.not_sold_here:
        out.append(f"\nNot sold online for this PIN: {', '.join(p.not_sold_here)}.")
    out += ["", "Cost and per-unit prices are before delivery; delivery is added per order. " + CAUTION,
            "", _LINK_NOTE, "", "### Run", _run_line(p.run)
            + (f" · {p.combinations_priced:,} basket combinations priced" if p.combinations_priced else "")]
    return "\n".join(out)


def _result(model: BaseModel, markdown: str, response_format: str) -> CallToolResult:
    data = model.model_dump(mode="json")
    body = json.dumps(data, ensure_ascii=False) if response_format == "json" else markdown
    return CallToolResult(content=[TextContent(type="text", text=body)], structured_content=data)


# ─────────────────────────────────────────────
# Progress (best effort; runs on the worker thread)
# ─────────────────────────────────────────────

_STAGE_TEXT = {
    "main": "Prices found, ranking by delivered cost",
    "main_update": "Listings re-ranked",
    "alternatives": "Same-salt brands compared",
    "main_links": "Product pages resolved",
    "basket": "Basket optimised",
    "basket_links": "Product pages resolved for the basket",
}


def _progress_reporter(ctx: Context):
    step = 0

    def on_event(name: str, data) -> None:
        nonlocal step
        if name == "call":
            text = f"SerpApi lookup {data['n']} ({data['tag']}): {'from cache' if not data['credit'] else '1 credit'}"
        elif name == "line" and isinstance(data, dict):
            text = f"{data.get('query')}: {data.get('status')}"
        elif name in _STAGE_TEXT:
            text = _STAGE_TEXT[name]
        else:
            return
        step += 1
        try:
            anyio.from_thread.run(ctx.report_progress, step, None, text)
        except Exception:  # client gone or request cancelled: progress is best-effort
            pass

    return on_event


# ─────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────

_SEARCH = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True)


@mcp.tool(title="Search medicine prices", annotations=_SEARCH)
async def search_medicine(
    query: Annotated[str, Field(min_length=2, max_length=120,
                                description="Medicine brand or salt with strength, e.g. 'Stamlo 5', 'Dolo 650', "
                                            "'Atorvastatin 10mg'. Spelling mistakes are corrected.")],
    pincode: Annotated[str, Field(max_length=20, description="6-digit Indian PIN code the medicine is delivered to, "
                                                             "e.g. '110001'. Delivery fees depend on it.")],
    ctx: Context,
    resolve_links: Annotated[bool, Field(description="Resolve product pages for the top 5 listings and cheaper "
                                                     "brands up front (up to ~8 extra credits). Prefer false and "
                                                     "get_buy_link for the listing the user picks.")] = False,
    response_format: ResponseFormat = "markdown",
) -> Annotated[CallToolResult, SearchOutput]:
    """Find where a medicine is cheapest in India once delivery to the PIN is included, plus cheaper same-salt brands.

    Searches Google Shopping (via SerpApi), keeps only listings that really are this medicine, adds each
    pharmacy's delivery and platform fee for the PIN code, and ranks by what the buyer pays. Brands with
    the same salt, strength and form (from a 246,000-medicine index) are compared per tablet, delivery
    included. A name without a strength ("paracetamol") returns the options in needs_strength instead
    of searching (0 credits). A new medicine costs about 4 SerpApi credits and 10-60 s; repeat or
    similar searches come from cache for 0 credits in under a second. Every listing has a listing_id
    for get_buy_link. Reports progress as stages finish.
    """
    on_event = _progress_reporter(ctx)
    try:
        result = await anyio.to_thread.run_sync(
            lambda: api.collect_search(query, pincode, resolve_links, True, on_event=on_event),
            abandon_on_cancel=True,  # the search keeps its slot and finishes; its results get cached
        )
    except api.SearchRejected as e:
        raise ToolError(f"{e.code}: {e.message}") from None
    if result["error"] and not result["listings"] and not result.get("choose"):
        raise ToolError(f"{result['error']['code']}: {result['error']['message']}")
    out = _search_output(result)
    return _result(out, _search_markdown(out), response_format)


class PrescriptionItem(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=120,
                               description="Medicine as written on the prescription: brand or salt with strength, "
                                           "e.g. 'Dolo 650', 'Atorvastatin 10mg'.")]
    tablets: Annotated[Optional[int], Field(default=None, ge=1, le=500,
                                            description="Tablets (or items, for syrups and creams) needed. "
                                                        "Omit to buy one pack.")] = None


@mcp.tool(title="Plan a prescription", annotations=_SEARCH)
async def plan_prescription(
    medicines: Annotated[list[PrescriptionItem], Field(min_length=1, max_length=8,
                                                       description="The prescription, one entry per medicine "
                                                                   "(up to 8).")],
    pincode: Annotated[str, Field(max_length=20, description="6-digit Indian PIN code the order is delivered to.")],
    ctx: Context,
    resolve_links: Annotated[bool, Field(description="Resolve product pages for the items in the chosen baskets "
                                                     "up front (1 credit each the first time). Prefer false and "
                                                     "get_buy_link for the items the user buys.")] = False,
    response_format: ResponseFormat = "markdown",
) -> Annotated[CallToolResult, PrescriptionOutput]:
    """Find the cheapest way to buy a whole prescription in India, delivery included.

    Every medicine is searched at the same time. Brands with the same salt, strength and form are
    compared, and the basket is optimised as a whole: each pharmacy's delivery fee and free-delivery
    threshold apply to its own order total, so two medicines in one order can beat buying each where
    it is cheapest alone. Returns three plans (cheapest with same-salt swaps, one pharmacy, exactly as
    prescribed) with their orders, the saving from swaps, a per-medicine comparison, and any medicine
    that needs a strength first (left out of the basket, 0 credits). About 4 SerpApi credits per new
    medicine; repeats come from cache for 0. Every item has a listing_id for get_buy_link.
    """
    items = [{"q": m.name, "tablets": m.tablets} for m in medicines]
    on_event = _progress_reporter(ctx)
    try:
        result = await anyio.to_thread.run_sync(
            lambda: api.collect_prescription(items, pincode, resolve_links, True, on_event=on_event),
            abandon_on_cancel=True)
    except api.SearchRejected as e:
        raise ToolError(f"{e.code}: {e.message}") from None
    if result["error"] and not result["basket"] and not any(
            ln.get("status") == "choose" for ln in result["lines"].values()):
        raise ToolError(f"{result['error']['code']}: {result['error']['message']}")
    out = _prescription_output(result)
    return _result(out, _plan_markdown(out), response_format)


@mcp.tool(
    title="Get a pharmacy product link",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True,
                                open_world_hint=True),
)
async def get_buy_link(
    listing_id: Annotated[str, Field(min_length=8, max_length=40,
                                     description="listing_id from a search_medicine or plan_prescription result.")],
    response_format: ResponseFormat = "markdown",
) -> Annotated[CallToolResult, BuyLinkOutput]:
    """Resolve a listing to the pharmacy's own product page, so the user can buy that exact offer.

    The same lookup the web app does when a Buy button is clicked: one SerpApi Google product-page call
    the first time (1 credit), then cached for 24 h (0 credits). Only that pharmacy's page is returned,
    never another store's. If the product page can't be found, the pharmacy's search page is returned
    with is_product_page false. Ids come from searches made by this server and expire when it restarts.
    """
    with api._links_lock:
        entry = api._links.get(listing_id)
    if entry is None:
        raise ToolError("unknown_listing: this listing id is unknown or has expired. "
                        "Run search_medicine or plan_prescription again and use an id from that result.")
    row, fallback = entry
    cache = api._get_cache(verbose=False)
    t0 = time.perf_counter()
    misses = cache.stats["misses"]
    try:
        url = await anyio.to_thread.run_sync(lambda: api._fetch_direct_link(row))
    except Exception as e:  # budget reached, SerpApi down: the message is already key-free
        log.warning("get_buy_link %s failed: %s", listing_id, api.redact(f"{type(e).__name__}: {e}"))
        url = ""
    spent = max(0, cache.stats["misses"] - misses)
    if not url and not fallback:
        raise ToolError(f"no_product_page: no product page found at {row.get('platform')}.")
    out = BuyLinkOutput(listing_id=listing_id, pharmacy=row.get("platform"), product=row.get("medicine_name"),
                        url=url or fallback, is_product_page=bool(url), credits_spent=spent,
                        seconds=round(time.perf_counter() - t0, 2))
    what = "Product page" if out.is_product_page else "Product page not found; the pharmacy's search page instead"
    md = (f"**{what}** for {out.product or 'this listing'} at {out.pharmacy}: {out.url}\n\n"
          f"{out.credits_spent} credit{'s' if out.credits_spent != 1 else ''} spent · {out.seconds:.1f} s")
    return _result(out, md, response_format)


def _lab_with_retry(query: str, top: int) -> dict:
    """api.cache_lab, retried once: right after Redis comes back, a parallel call can see the reconnect
    still in progress and report Redis down."""
    try:
        return api.cache_lab(q=query, top=top)
    except HTTPException as e:
        if e.status_code != 503 or "Redis" not in str(e.detail):
            raise
        time.sleep(1.0)
        cache = api._get_cache(verbose=False)
        cache._next_reconnect = 0.0  # allow an immediate reconnect attempt
        return api.cache_lab(q=query, top=top)


@mcp.tool(
    title="Cache Lab: predict a cache decision",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
)
def cache_lab(
    query: Annotated[str, Field(min_length=1, max_length=120,
                                description="A medicine search as a user would type it, e.g. 'Dolo 500'.")],
    top: Annotated[int, Field(ge=1, le=20, description="How many nearest cached queries to list.")] = 6,
    response_format: ResponseFormat = "markdown",
) -> Annotated[CallToolResult, LabOutput]:
    """Show what the semantic cache would do with a price search for this query, without searching.

    Walks the real decision chain: normalized exact key, embedding cosine similarity against every
    cached query with the same parameters, the 0.88 threshold, and the dosage guard (different numbers
    never share results). Reads Redis only and costs 0 credits. Predicts the main price lookup only.
    """
    try:
        lab = _lab_with_retry(query, top)
    except HTTPException as e:
        raise ToolError(str(e.detail)) from None
    out = LabOutput(input=lab["input"], decision=lab["decision"], reason=lab["reason"],
                    credits_if_searched=lab["credits"], normalized_query=lab["normalized_query"],
                    threshold=lab["threshold"], compared_against=lab["compared_against"],
                    timings_ms=lab["timings_ms"],
                    nearest=[NearQuery(cached_query=c["query_text"].split(" | ")[0], similarity=c["similarity"],
                                       above_threshold=c["above_threshold"], same_params=c["same_params"],
                                       dosage_guard_blocks=c["dosage_guard_blocks"]) for c in lab["nearest"]])
    verdict = {"exact_hit": "EXACT HIT (0 credits)", "semantic_hit": "SEMANTIC HIT (0 credits)",
               "api_call": "SERPAPI CALL (1 credit)"}[out.decision]
    t = out.timings_ms
    md = [f"## Cache Lab: \"{out.input}\"", "",
          f"Decision: **{verdict}**. {out.reason}.", "",
          f"Normalized query `{out.normalized_query}` · threshold {out.threshold} · compared against "
          f"{out.compared_against} cached queries · exact lookup {t.get('exact_lookup')} ms, embed {t.get('embed')} ms, "
          f"scan {t.get('scan')} ms", ""]
    if out.nearest:
        md += ["| Cached query | Similarity | ≥ threshold | Same params | Dosage guard |", "|---|---|---|---|---|"]
        md += [f"| {_cell(c.cached_query)} | {c.similarity:.3f} | {'yes' if c.above_threshold else 'no'} | "
               f"{'yes' if c.same_params else 'NO'} | {'BLOCKS' if c.dosage_guard_blocks else '—'} |" for c in out.nearest]
    else:
        md.append("No cached price searches to compare against.")
    return _result(out, "\n".join(md), response_format)


@mcp.tool(
    title="Cache statistics",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=False, open_world_hint=False),
)
def cache_stats(response_format: ResponseFormat = "markdown") -> Annotated[CallToolResult, StatsOutput]:
    """Report Redis status, what is cached (by kind, with size), and credits spent vs saved.

    Counters cover searches made through this MCP server process since it started. Costs 0 credits.
    """
    health, entries, stats = api.health(), api.cache_entries(), api.stats()
    out = StatsOutput(redis_ok=health["redis_ok"], embedding_model=str(health["model"]),
                      similarity_threshold=health["similarity_threshold"],
                      serpapi_key_configured=health["serpapi_key_configured"],
                      gemini_key_configured=health["gemini_key_configured"],
                      cached_entries=entries["counts"], cached_bytes=int(entries.get("total_bytes") or 0),
                      session=stats["session"])
    s = out.session
    counts = ", ".join(f"{v} {k}" for k, v in out.cached_entries.items()) or "nothing"
    md = "\n".join([
        "## PharmaWatch cache",
        "",
        f"- Redis: {'up' if out.redis_ok else 'DOWN (passthrough: every lookup costs a credit)'}",
        f"- Embedding model: {out.embedding_model} · similarity threshold {out.similarity_threshold}",
        f"- Keys configured: SerpApi {'yes' if out.serpapi_key_configured else 'no'}, "
        f"Gemini {'yes' if out.gemini_key_configured else 'no'}",
        f"- Cached: {counts} ({out.cached_bytes / 1024:.1f} KB)",
        f"- This session: {s['searches']} searches, {s['serpapi_calls']} lookups, {s['credits_spent']} credits spent, "
        f"{s['credits_saved']} saved ({s['exact_hits']} exact, {s['semantic_hits']} semantic, "
        f"hit rate {s['hit_rate_pct']}%)",
    ])
    return _result(out, md, response_format)


# ─────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────

@mcp.prompt(title="Compare a medicine's prices")
def compare_medicine(medicine: str, pincode: str) -> str:
    """Where is this medicine cheapest delivered to my PIN, and is there a cheaper same-salt brand?"""
    return (f"Find where {medicine} is cheapest delivered to PIN {pincode} in India. Use the PharmaWatch "
            "search_medicine tool. If it asks which strength, ask me before searching again. Show the 5 cheapest "
            "offers by the price I actually pay (delivery included) with pharmacy, delivery and arrival time, then "
            "any cheaper brand with the same salt and strength and how much it saves per tablet. Remind me to check "
            "with my doctor or pharmacist before switching brands. When I pick an offer, use get_buy_link to give me "
            "the pharmacy's product page.")


@mcp.prompt(title="Plan my prescription")
def plan_my_prescription(prescription: str, pincode: str) -> str:
    """Cheapest way to buy a whole prescription, delivery included."""
    return (f"Here is my prescription, one medicine per line (with the number of tablets if given):\n{prescription}\n\n"
            f"Find the cheapest way to buy all of it delivered to PIN {pincode}. Use the PharmaWatch "
            "plan_prescription tool. Show the cheapest plan as orders per pharmacy with each item, packs and cost, the "
            "delivery per order and the total, then the one-pharmacy and exactly-as-prescribed totals for comparison. "
            "Mark same-salt swaps and remind me to check them with my doctor or pharmacist. If a medicine needs a "
            "strength, ask me. When I'm ready to buy, use get_buy_link for each item I choose.")


# ─────────────────────────────────────────────
# Schemas: inline every $ref
# ─────────────────────────────────────────────

def _inline_refs(schema: Optional[dict]) -> Optional[dict]:
    """Replace "$ref": "#/$defs/X" with the definition itself and drop $defs. Some MCP clients don't
    resolve $defs and would show list items as {} (no name / tablets fields)."""
    if not schema or "$defs" not in schema:
        return schema
    defs = schema["$defs"]

    def walk(node, seen=()):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.split("/")[-1]
                if name in seen:  # recursive model: keep a plain object rather than loop
                    return {"type": "object"}
                merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
                return walk(merged, seen + (name,))
            return {k: walk(v, seen) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v, seen) for v in node]
        return node

    return walk(schema)


for _tool in mcp._tool_manager.list_tools():
    _tool.parameters = _inline_refs(_tool.parameters)
    if _tool.fn_metadata.output_schema is not None:
        _tool.fn_metadata.output_schema = _inline_refs(_tool.fn_metadata.output_schema)


# ─────────────────────────────────────────────
# stdio
# ─────────────────────────────────────────────

async def _serve_stdio(wire_fd: int) -> None:
    wire = anyio.wrap_file(io.TextIOWrapper(os.fdopen(wire_fd, "wb"), encoding="utf-8"))
    async with stdio_server(stdout=wire) as (read_stream, write_stream):
        # Same as MCPServer.run_stdio_async, with an explicit stdout (no public hook for one).
        await mcp._lowlevel_server.run(read_stream, write_stream,
                                       mcp._lowlevel_server.create_initialization_options())


def main() -> None:
    # The protocol gets a private copy of stdout; fd 1 and sys.stdout point at stderr for the whole
    # run. The SDK's own diversion is undone at shutdown, when Python flushes buffered prints (the
    # cache's "Redis connected") — those bytes then landed on the wire and broke the client's parser.
    sys.stdout.flush()
    wire_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    anyio.run(_serve_stdio, wire_fd)


if __name__ == "__main__":
    main()
