"""
mcp_server.py — PharmaWatch as an MCP server (stdio), for Claude Desktop, MCP Inspector or any MCP client.

Tools (all thin wrappers over api/main.py, so validation, the concurrency limit, the search
deadline and credit accounting are the same as the HTTP API):

  search_medicine(query, pincode, resolve_links=False)   delivered prices + cheaper generics
  cache_lab(query)                                       what the cache would do, 0 credits
  cache_stats()                                          Redis contents + hit/credit counters

Output is Markdown by default (compact, for LLM context) or JSON with response_format="json".
The protocol owns stdout: main() serves it on a private copy and points fd 1 and sys.stdout at
stderr, so the cache's console prints and library warnings go to the client's server log.

Run from anywhere:
    python mcp_server.py
    npx @modelcontextprotocol/inspector python mcp_server.py
"""

import io
import json
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")  # MCP clients start servers from any working directory

import anyio  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from mcp.server.mcpserver import Context, MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402
from pydantic import Field  # noqa: E402

import api.main as api  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402

log = logging.getLogger("pharmawatch.mcp")

MAX_ROWS = 10  # listings shown in Markdown; the rest are counted, keeping the tool result small
ResponseFormat = Annotated[
    Literal["markdown", "json"],
    Field(description="'markdown' (default) is compact and readable; 'json' is for programmatic use."),
]


@asynccontextmanager
async def lifespan(server: MCPServer):
    # Build the shared cache before any request can: _get_cache is not locked, and a warm-up thread
    # racing the first tool call would create two caches and load the model twice at once.
    await anyio.to_thread.run_sync(lambda: _get_cache(verbose=False))
    # Load the embedding model off the request path (~40 s once), exactly like the HTTP API.
    threading.Thread(target=api._warm, daemon=True, name="warm-up").start()
    yield


mcp = MCPServer(
    name="pharmawatch",
    title="PharmaWatch",
    version="0.1.0",
    instructions=(
        "Indian medicine prices, ranked by what the buyer actually pays delivered to their PIN code, "
        "plus cheaper generics with the same salt and strength. Prices are live Google Shopping data via "
        "SerpApi, cached in Redis for 24 h. A new medicine costs up to ~12 SerpApi credits; a repeat or "
        "similar search is served from cache for 0. Call cache_lab first if credits matter: it predicts "
        "whether the main price lookup would hit the cache, for free. Keep resolve_links false unless the "
        "user needs direct pharmacy URLs (each resolved link can cost a credit)."
    ),
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# Formatting
# ─────────────────────────────────────────────

def _inr(value) -> str:
    return "—" if value is None else f"₹{value:,.2f}"


def _cell(text) -> str:
    return str(text or "—").replace("|", "\\|").replace("\n", " ")


def _link(row: dict) -> str:
    url = row.get("direct_link") or row.get("search_link") or row.get("google_link")
    return f"[open]({url})" if url else "—"


def _pack(alt: dict) -> str:
    if not alt.get("pack_size"):
        return "—"
    return f"~{alt['pack_size']} (est.)" if alt.get("pack_estimated") else str(alt["pack_size"])


def _summary_line(summary: dict | None) -> str:
    if not summary:
        return "No run summary."
    spent = summary["credits_spent"]
    return (f"{summary['calls']} SerpApi lookups · {spent} credit{'' if spent == 1 else 's'} spent · "
            f"{summary['credits_saved']} served from cache ({summary['exact_hits']} exact, "
            f"{summary['semantic_hits']} semantic) · {summary['total_ms'] / 1000:.1f} s")


def _search_markdown(r: dict) -> str:
    out = [f"## {r['query']}: delivered prices to PIN {r['pincode']}", ""]
    if r["error"]:
        out += [f"> **Search incomplete ({r['error']['code']}):** {r['error']['message']}", ""]

    rows = r["listings"] or []
    if rows:
        best = next((x for x in rows if x.get("is_cheapest")), None)
        if best:
            out += [f"Cheapest delivered: **{_inr(best['total_landed_cost'])}** at {best['platform']} "
                    f"({best.get('delivery_label') or best.get('delivery_status')}).", ""]
        out += ["| # | Pharmacy | Product | Shelf price | Delivery | You pay | Arrives | Link |",
                "|---|---|---|---|---|---|---|---|"]
        for i, x in enumerate(rows[:MAX_ROWS], 1):
            out.append(f"| {x.get('rank') or i} | {_cell(x['platform'])} | {_cell(x['medicine_name'])} | "
                       f"{_inr(x['price_inr'])} | {_cell(x.get('delivery_label'))} | "
                       f"{_inr(x.get('total_landed_cost'))} | {_cell(x.get('estimated_days'))} | {_link(x)} |")
        if len(rows) > MAX_ROWS:
            out.append(f"\n{len(rows) - MAX_ROWS} more listings not shown (response_format='json' has all).")
    else:
        out.append("No listings found for this medicine.")

    alts = r["alternatives"]
    out.append("")
    if not alts:
        out.append("### Generic alternatives\nNot in the composition catalogue, so no substitutes were searched.")
    else:
        comp = alts.get("composition") or {}
        out.append(f"### Generic alternatives: {comp.get('active_ingredient') or comp.get('name', '')}")
        ref = alts.get("reference")
        if ref:
            unit = f", {_inr(ref['unit_landed_cost'])}/tablet" if ref.get("unit_landed_cost") is not None else ""
            out.append(f"Reference: {_cell(ref.get('medicine_name'))} at {_inr(ref.get('total_landed_cost'))}{unit}.")
        cheaper = alts.get("cheaper_alternatives") or []
        if cheaper:
            out += ["", "| Brand | Pharmacy | You pay | Per tablet | Pack | Saving |", "|---|---|---|---|---|---|"]
            for a in cheaper:
                basis = "/tablet" if a.get("price_basis") == "per_tablet" else ""
                approx = "≈" if a.get("estimated") else ""
                saving = (f"{approx}{a['savings_pct']}% ({_inr(a.get('savings'))}{basis})"
                          if a.get("savings_pct") is not None else "—")
                out.append(f"| {_cell(a.get('brand'))} | {_cell(a.get('platform'))} | {_inr(a.get('total_landed_cost'))} | "
                           f"{_inr(a.get('unit_landed_cost'))} | {_pack(a)} | {saving} |")
            out.append("\n~ = pack size estimated, ≈ = saving depends on it.")
        else:
            out.append("No cheaper substitute found online right now.")
        if alts.get("not_found"):
            out.append(f"Not sold online at the moment: {', '.join(alts['not_found'])}.")

    out += ["", "### Run", _summary_line(r["summary"])]
    return "\n".join(out)


_LISTING_KEYS = ("rank", "platform", "medicine_name", "price_inr", "delivery_fee", "delivery_status",
                 "delivery_label", "total_landed_cost", "estimated_days", "is_cheapest")
_ALT_KEYS = ("brand", "medicine_name", "platform", "total_landed_cost", "unit_landed_cost", "pack_size",
             "pack_estimated", "savings", "savings_pct", "price_basis", "estimated")


def _pick(row: dict | None, keys) -> dict | None:
    if not row:
        return row
    out = {k: row.get(k) for k in keys}
    url = row.get("direct_link") or row.get("search_link") or row.get("google_link")
    if url:
        out["link"] = url
    return out


def _search_json(r: dict) -> str:
    alts = r["alternatives"]
    if alts:
        alts = {
            "composition": alts.get("composition"),
            "matched_by": alts.get("matched_by"),
            "reference": _pick(alts.get("reference"), _ALT_KEYS),
            "cheaper_alternatives": [_pick(a, _ALT_KEYS) for a in alts.get("cheaper_alternatives") or []],
            "not_found": alts.get("not_found") or [],
        }
    return json.dumps({
        "query": r["query"], "pincode": r["pincode"],
        "listings": [_pick(x, _LISTING_KEYS) for x in r["listings"] or []],
        "alternatives": alts, "summary": r["summary"], "error": r["error"],
    }, ensure_ascii=False)


# ─────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────

_PROGRESS_TEXT = {
    "main": "Prices found, ranking by delivered cost",
    "main_update": "Listings re-ranked",
    "alternatives": "Generic alternatives ready",
    "main_links": "Direct pharmacy links resolved",
}


@mcp.tool(
    title="Search medicine prices",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True,
                                open_world_hint=True),
    structured_output=False,
)
async def search_medicine(
    query: Annotated[str, Field(min_length=2, max_length=120,
                                description="Medicine brand or salt with strength, e.g. 'Stamlo 5', 'Dolo 650', "
                                            "'Atorvastatin 10mg'.")],
    pincode: Annotated[str, Field(max_length=20, description="6-digit Indian PIN code the medicine is delivered to, "
                                                             "e.g. '110001'. Delivery fees depend on it.")],
    ctx: Context,
    resolve_links: Annotated[bool, Field(description="Resolve direct pharmacy URLs for the top listings. "
                                                     "Costs extra SerpApi credits; leave false unless asked.")] = False,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Find where a medicine is cheapest in India once delivery is included, and cheaper generics.

    Searches Google Shopping (via SerpApi) for the medicine, adds each pharmacy's delivery fee for the
    PIN code, and ranks listings by the total the buyer pays. If the medicine is in the composition
    catalogue, it also searches brands with the same salt and strength and reports per-tablet savings.
    A new medicine costs up to ~12 SerpApi credits and ~10-60 s; repeat or similar searches come from
    cache for 0 credits in well under a second. Reports progress as stages finish.
    """
    step = 0

    def on_event(name: str, data) -> None:  # runs on the worker thread
        nonlocal step
        if name == "call":
            text = f"SerpApi lookup {data['n']} ({data['tag']}): {data['kind']}"
        elif name in _PROGRESS_TEXT:
            text = _PROGRESS_TEXT[name]
        else:
            return
        step += 1
        try:
            anyio.from_thread.run(ctx.report_progress, step, None, text)
        except Exception:  # client gone or request cancelled: progress is best-effort
            pass

    try:
        result = await anyio.to_thread.run_sync(
            lambda: api.collect_search(query, pincode, resolve_links, True, on_event=on_event),
            abandon_on_cancel=True,  # the search keeps its slot and finishes; its results get cached
        )
    except api.SearchRejected as e:
        raise ToolError(f"{e.code}: {e.message}") from None

    if result["error"] and not result["listings"]:
        raise ToolError(f"{result['error']['code']}: {result['error']['message']}")
    return _search_json(result) if response_format == "json" else _search_markdown(result)


@mcp.tool(
    title="Cache Lab: predict a cache decision",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    structured_output=False,
)
def cache_lab(
    query: Annotated[str, Field(min_length=1, max_length=120,
                                description="A medicine search as a user would type it, e.g. 'Dolo 500'.")],
    top: Annotated[int, Field(ge=1, le=20, description="How many nearest cached queries to list.")] = 6,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Show what the semantic cache would do with a price search for this query, without searching.

    Walks the real decision chain: normalized exact key, embedding cosine similarity against every
    cached query, the 0.88 threshold, and the dosage guard (different numbers never share results).
    Reads Redis only and costs 0 credits. Predicts the main price lookup only, not substitute searches.
    """
    try:
        lab = api.cache_lab(q=query, top=top)
    except HTTPException as e:
        raise ToolError(str(e.detail)) from None
    if response_format == "json":
        return json.dumps(lab, ensure_ascii=False)

    verdict = {"exact_hit": "EXACT HIT (0 credits)", "semantic_hit": "SEMANTIC HIT (0 credits)",
               "api_call": "SERPAPI CALL (1 credit)"}[lab["decision"]]
    t = lab["timings_ms"]
    out = [f"## Cache Lab: \"{lab['input']}\"", "",
           f"Decision: **{verdict}**. {lab['reason']}.", "",
           f"Normalized query `{lab['normalized_query']}` · threshold {lab['threshold']} · compared against "
           f"{lab['compared_against']} cached queries · exact lookup {t['exact_lookup']} ms, embed {t['embed']} ms, "
           f"scan {t['scan']} ms", ""]
    if lab["nearest"]:
        out += ["| Cached query | Similarity | ≥ threshold | Dosage guard |", "|---|---|---|---|"]
        for c in lab["nearest"]:
            out.append(f"| {_cell(c['query_text'].split(' | ')[0])} | {c['similarity']:.3f} | "
                       f"{'yes' if c['above_threshold'] else 'no'} | {'BLOCKS' if c['dosage_guard_blocks'] else '—'} |")
    else:
        out.append("No cached price searches to compare against.")
    return "\n".join(out)


@mcp.tool(
    title="Cache statistics",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=False, open_world_hint=False),
    structured_output=False,
)
def cache_stats(response_format: ResponseFormat = "markdown") -> str:
    """Report Redis status, what is cached (by kind, with size), and credits spent vs saved.

    Counters cover searches made through this MCP server process since it started. Costs 0 credits.
    """
    health, entries, stats = api.health(), api.cache_entries(), api.stats()
    data = {
        "redis_ok": health["redis_ok"],
        "embedding_model": health["model"],
        "similarity_threshold": health["similarity_threshold"],
        "serpapi_key_configured": health["serpapi_key_configured"],
        "gemini_key_configured": health["gemini_key_configured"],
        "cached_entries": entries["counts"],
        "cached_bytes": entries.get("total_bytes", 0),
        "session": stats["session"],
    }
    if response_format == "json":
        return json.dumps(data, ensure_ascii=False)

    s = data["session"]
    counts = ", ".join(f"{v} {k}" for k, v in data["cached_entries"].items()) or "nothing"
    return "\n".join([
        "## PharmaWatch cache",
        "",
        f"- Redis: {'up' if data['redis_ok'] else 'DOWN (passthrough: every lookup costs a credit)'}",
        f"- Embedding model: {data['embedding_model']} · similarity threshold {data['similarity_threshold']}",
        f"- Keys configured: SerpApi {'yes' if data['serpapi_key_configured'] else 'no'}, "
        f"Gemini {'yes' if data['gemini_key_configured'] else 'no'}",
        f"- Cached: {counts} ({data['cached_bytes'] / 1024:.1f} KB)",
        f"- This session: {s['searches']} searches, {s['serpapi_calls']} lookups, {s['credits_spent']} credits spent, "
        f"{s['credits_saved']} saved ({s['exact_hits']} exact, {s['semantic_hits']} semantic, "
        f"hit rate {s['hit_rate_pct']}%)",
    ])


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
