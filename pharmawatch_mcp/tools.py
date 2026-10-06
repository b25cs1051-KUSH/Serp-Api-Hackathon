"""
The five tools. Each one calls the same code as the web app's HTTP API (api/main.py), so validation,
the concurrency limit, the search deadline, the daily credit budget and credit accounting are shared,
then returns Markdown text plus structuredContent that matches its outputSchema.
"""

import json
import logging
import time
from typing import Annotated

import anyio
import api.main as api
from fastapi import HTTPException
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from . import convert, render
from .app import mcp
from .models import (
    BuyLinkOutput,
    LabOutput,
    PrescriptionItem,
    PrescriptionOutput,
    ResponseFormat,
    SearchOutput,
    StatsOutput,
)

log = logging.getLogger("pharmawatch.mcp")

SEARCH_ANNOTATIONS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True,
                                     open_world_hint=True)
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)

_STAGE_TEXT = {
    "main": "Prices found, ranking by delivered cost",
    "main_update": "Listings re-ranked",
    "alternatives": "Same-salt brands compared",
    "main_links": "Product pages resolved",
    "basket": "Basket optimised",
    "basket_links": "Product pages resolved for the basket",
}


def _result(model: BaseModel, markdown: str, response_format: str) -> CallToolResult:
    data = model.model_dump(mode="json")
    body = json.dumps(data, ensure_ascii=False) if response_format == "json" else markdown
    return CallToolResult(content=[TextContent(type="text", text=body)], structured_content=data)


def _progress(ctx: Context):
    """An on_event callback for the API's collectors that reports MCP progress (runs on the worker thread)."""
    step = 0

    def on_event(name: str, data) -> None:
        nonlocal step
        if name == "call":
            text = f"SerpApi lookup {data['n']} ({data['tag']}): {'1 credit' if data['credit'] else 'from cache'}"
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


async def _collect(fn):
    """Run an API collector off the event loop. Rejected input becomes a tool error before anything is spent."""
    try:
        # abandon_on_cancel: a cancelled search keeps its slot and finishes, so its results still get cached
        return await anyio.to_thread.run_sync(fn, abandon_on_cancel=True)
    except api.SearchRejected as e:
        raise ToolError(f"{e.code}: {e.message}") from None


# ── search_medicine ──────────────────────────────────────────────────────────

@mcp.tool(title="Search medicine prices", annotations=SEARCH_ANNOTATIONS)
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
    on_event = _progress(ctx)
    result = await _collect(lambda: api.collect_search(query, pincode, resolve_links, True, on_event=on_event))
    if result["error"] and not result["listings"] and not result.get("choose"):
        raise ToolError(f"{result['error']['code']}: {result['error']['message']}")
    out = convert.search_output(result)
    return _result(out, render.search(out), response_format)


# ── plan_prescription ────────────────────────────────────────────────────────

@mcp.tool(title="Plan a prescription", annotations=SEARCH_ANNOTATIONS)
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
    on_event = _progress(ctx)
    result = await _collect(lambda: api.collect_prescription(items, pincode, resolve_links, True, on_event=on_event))
    needs_strength = any(ln.get("status") == "choose" for ln in result["lines"].values())
    if result["error"] and not result["basket"] and not needs_strength:
        raise ToolError(f"{result['error']['code']}: {result['error']['message']}")
    out = convert.prescription_output(result)
    return _result(out, render.prescription(out), response_format)


# ── get_buy_link ─────────────────────────────────────────────────────────────

@mcp.tool(title="Get a pharmacy product link", annotations=SEARCH_ANNOTATIONS)
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
    t0, misses = time.perf_counter(), cache.stats["misses"]
    try:
        url = await anyio.to_thread.run_sync(lambda: api._fetch_direct_link(row))
    except Exception as e:  # budget reached, SerpApi down: fall back to the store page
        log.warning("get_buy_link %s failed: %s", listing_id, api.redact(f"{type(e).__name__}: {e}"))
        url = ""
    if not url and not fallback:
        raise ToolError(f"no_product_page: no product page found at {row.get('platform')}.")
    out = BuyLinkOutput(listing_id=listing_id, pharmacy=row.get("platform"), product=row.get("medicine_name"),
                        url=url or fallback, is_product_page=bool(url),
                        credits_spent=max(0, cache.stats["misses"] - misses),
                        seconds=round(time.perf_counter() - t0, 2))
    return _result(out, render.buy_link(out), response_format)


# ── cache_lab ────────────────────────────────────────────────────────────────

def _lab_with_retry(query: str, top: int) -> dict:
    """api.cache_lab, retried once: right after Redis comes back, a parallel call can see the reconnect
    still in progress and report Redis down."""
    try:
        return api.cache_lab(q=query, top=top)
    except HTTPException as e:
        if e.status_code != 503 or "Redis" not in str(e.detail):
            raise
        time.sleep(1.0)
        api._get_cache(verbose=False)._next_reconnect = 0.0  # allow an immediate reconnect attempt
        return api.cache_lab(q=query, top=top)


@mcp.tool(title="Cache Lab: predict a cache decision", annotations=READ_ONLY)
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
        out = convert.lab_output(_lab_with_retry(query, top))
    except HTTPException as e:
        raise ToolError(str(e.detail)) from None
    return _result(out, render.lab(out), response_format)


# ── cache_stats ──────────────────────────────────────────────────────────────

@mcp.tool(title="Cache statistics",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=False, open_world_hint=False))
def cache_stats(response_format: ResponseFormat = "markdown") -> Annotated[CallToolResult, StatsOutput]:
    """Report Redis status, what is cached (by kind, with size), and credits spent vs saved.

    Counters cover searches made through this server process since it started. Costs 0 credits.
    """
    health, entries, stats = api.health(), api.cache_entries(), api.stats()
    out = StatsOutput(redis_ok=health["redis_ok"], embedding_model=str(health["model"]),
                      similarity_threshold=health["similarity_threshold"],
                      serpapi_key_configured=health["serpapi_key_configured"],
                      gemini_key_configured=health["gemini_key_configured"],
                      cached_entries=entries["counts"], cached_bytes=int(entries.get("total_bytes") or 0),
                      session=stats["session"])
    return _result(out, render.stats(out), response_format)
