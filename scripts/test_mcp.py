"""
test_mcp.py — Checks for mcp_server.py (0 SerpApi credits, no Gemini).

Part 1 talks to the server in memory with the pipeline stubbed (same stub shape as test_api.py):
tool list, schemas, annotations, Markdown and JSON output, progress, input and pipeline errors.
Part 2 starts `python mcp_server.py` as a real stdio subprocess from another working directory,
as Claude Desktop does, and calls tools that cannot spend credits. This proves stdout carries
only protocol messages even though the cache prints to the console.

    python scripts/test_mcp.py        (Redis should be running: docker compose up -d)
"""

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import anyio  # noqa: E402
from mcp import StdioServerParameters  # noqa: E402
from mcp.client import Client  # noqa: E402

import api.main as api  # noqa: E402
import mcp_server  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402

CACHE = _get_cache(verbose=False)
calls_made = []
results = []


def check(name, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" (expected {expected!r})"))
    results.append(ok)


def text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


def listing(title, price, token="tok-123"):
    return {"platform": "Chemist180", "medicine_name": title, "price_inr": price, "total_landed_cost": price,
            "delivery_status": "free", "delivery_label": "Free delivery", "is_cheapest": True, "rank": 1,
            "direct_link": "", "search_link": "https://chemist180.com/search?q=x", "page_token": token}


def log_call(tag, outcome, credit):
    now = time.perf_counter()
    with CACHE._log_lock:
        CACHE.call_log.append({"start": now, "end": now + 0.004, "engine": "google_shopping",
                               "query": tag, "outcome": outcome, "credit": credit, "tag": tag})


def stub_pipeline(fail=False):
    def fake(query, pincode, resolve_links=True, use_llm=True, verbose=False):
        calls_made.append((query, pincode, resolve_links))
        log_call("main search", "api_call", True)
        yield "main", [listing("Stamlo 5MG Tablet", 66.02)]
        if fail:
            raise RuntimeError("SerpApi exploded")
        log_call("substitute search: Amlokind 5", "exact_hit", False)
        log_call("substitute search: Amtas 5", "semantic_hit (0.912)", False)
        amlokind = dict(listing("Amlokind 5MG Tablet", 19.41), brand="Amlokind 5", unit_landed_cost=1.94,
                        pack_size=10, pack_estimated=True, savings=4.66, savings_pct=70.6,
                        price_basis="per_tablet", estimated=True)
        yield "alternatives", {
            "composition": {"name": "Amlodipine 5 mg", "active_ingredient": "Amlodipine", "drug_class": "CCB",
                            "brands": ["Stamlo 5", "Amlokind 5", "Amtas 5"]},
            "reference": dict(listing("Stamlo 5MG Tablet", 66.02), unit_landed_cost=6.60),
            "cheaper_alternatives": [amlokind], "other_alternatives": [], "not_found": ["Amtas 5"],
            "suggested_alternatives": ["Amlokind 5", "Amtas 5"], "matched_by": "exact",
        }
    return fake


async def part1_in_memory():
    print("\nPart 1: in-memory client, stubbed pipeline")
    real = api.search_medicine_stream
    try:
        async with Client(mcp_server.mcp) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            check("tools", sorted(tools), ["cache_lab", "cache_stats", "plan_prescription", "search_medicine"])
            rx = tools["plan_prescription"]
            check("prescription tool: medicines + pincode required", sorted(rx.input_schema.get("required", [])),
                  ["medicines", "pincode"])
            s = tools["search_medicine"]
            check("search required args", sorted(s.input_schema.get("required", [])), ["pincode", "query"])
            check("ctx hidden from schema", "ctx" in s.input_schema["properties"], False)
            check("resolve_links defaults false", s.input_schema["properties"]["resolve_links"]["default"], False)
            check("search annotations", (s.annotations.read_only_hint, s.annotations.destructive_hint,
                                         s.annotations.open_world_hint), (False, False, True))
            check("lab is read-only", tools["cache_lab"].annotations.read_only_hint, True)
            check("stats is read-only", tools["cache_stats"].annotations.read_only_hint, True)
            check("every tool documented", all(t.description and t.title for t in tools.values()), True)

            api.search_medicine_stream = stub_pipeline()
            progress = []

            async def on_progress(p, total, message):
                progress.append((p, message))

            r = await client.call_tool("search_medicine", {"query": "Stamlo 5", "pincode": "110001"},
                                       progress_callback=on_progress)
            md = text(r)
            check("search ok", r.is_error, False)
            check("markdown heading", md.startswith("## Stamlo 5: delivered prices to PIN 110001"), True)
            check("cheapest line", "Cheapest delivered: **₹66.02** at Chemist180" in md, True)
            check("generic row", "| Amlokind 5 | — | Chemist180 | ₹19.41 | ₹1.94 | ~10 (est.) | ≈70.6% (₹4.66/tablet) |" in md, True)
            check("not found listed", "Searched, but not sold online here right now: Amtas 5." in md, True)
            check("run line", "3 SerpApi lookups · 1 credit spent · 2 served from cache (1 exact, 1 semantic)" in md, True)
            check("no page tokens leak", "tok-123" in md, False)
            check("resolve_links passed as False", calls_made[-1], ("Stamlo 5", "110001", False))
            check("progress reported", len(progress) >= 4, True)
            check("progress increases", [p for p, _ in progress] == sorted(p for p, _ in progress), True)
            check("progress names stages", any("Generic alternatives ready" == m for _, m in progress), True)

            r = await client.call_tool("search_medicine", {"query": "Stamlo 5", "pincode": "110001",
                                                           "response_format": "json"})
            data = json.loads(text(r))
            check("json listings", len(data["listings"]), 1)
            check("json link, no token", ("link" in data["listings"][0], "page_token" in data["listings"][0]), (True, False))
            check("json cheaper", data["alternatives"]["cheaper_alternatives"][0]["savings_pct"], 70.6)
            check("json summary credits", data["summary"]["credits_spent"], 1)

            n = len(calls_made)
            r = await client.call_tool("search_medicine", {"query": "Stamlo 5", "pincode": "12345"})
            check("bad PIN is a tool error", (r.is_error, "invalid_pincode" in text(r)), (True, True))
            r = await client.call_tool("search_medicine", {"query": "1", "pincode": "110001"})
            check("short query rejected by schema", r.is_error, True)
            r = await client.call_tool("search_medicine", {"query": "12345", "pincode": "110001"})
            check("no-letter query is a tool error", (r.is_error, "invalid_query" in text(r)), (True, True))
            check("rejected searches never ran", len(calls_made), n)

            api.search_medicine_stream = stub_pipeline(fail=True)
            r = await client.call_tool("search_medicine", {"query": "Stamlo 5", "pincode": "110001"})
            md = text(r)
            check("partial result kept on failure", (r.is_error, "Search incomplete (pipeline_error)" in md,
                                                     "₹66.02" in md), (False, True, True))

            def choose_stub(query, pincode, resolve_links=True, use_llm=True, verbose=False):
                yield "choose", {"query": query, "reason": "strength not given",
                                 "options": [{"label": "Paracetamol 650mg tablet", "query": "Paracetamol 650mg", "comp_key": "k"}]}
            api.search_medicine_stream = choose_stub

            def rx_stub(lines, pincode, resolve_links=False, use_llm=True, verbose=False):
                log_call("line 1 main: Dolo 650", "exact_hit", False)
                yield "line", {"line": 1, "query": "paracetamol", "status": "choose",
                               "choose": {"query": "paracetamol", "reason": "strength not given",
                                          "options": [{"label": "Paracetamol 650mg tablet", "query": "Paracetamol 650mg"}]}}
                offer = {"line": 0, "brand": "Paracip 650", "platform": "Chemist180", "packs": 3, "pack_size": 10,
                         "pack_estimated": True, "item_cost": 41.82, "per_tablet": 1.39, "prescribed": False,
                         "search_link": "https://chemist180.com/s", "page_token": "tok-x"}
                plan = {"total": 41.82, "items_total": 41.82, "fees_total": 0.0,
                        "stores": [{"platform": "Chemist180", "lines": [offer], "subtotal": 41.82, "fee": 0.0,
                                    "delivery_label": "FREE", "free_delivery": True, "total": 41.82}]}
                yield "basket", {"with_swaps": {"best": plan, "single_store": plan, "lines": [0]},
                                 "as_prescribed": {"best": None, "single_store": None, "lines": []},
                                 "saving": 10.82, "saving_lines": [0], "per_line": [], "unavailable": [],
                                 "skipped": [1], "stats": {"combinations": 1, "ms": 0.1}}
            real_rx = api.prescription_stream
            api.prescription_stream = rx_stub
            try:
                r = await client.call_tool("plan_prescription", {"medicines": [{"name": "Dolo 650", "tablets": 30},
                                                                                {"name": "paracetamol"}],
                                                                  "pincode": "110001"})
            finally:
                api.prescription_stream = real_rx
            md = text(r)
            check("prescription: basket in markdown", (r.is_error, "**Cheapest basket: ₹41.82**" in md,
                                                       "| Chemist180 | Dolo 650 | Paracip 650 (same-salt swap) | 3 × ~10 |" in md),
                  (False, True, True))
            check("prescription: asks for the missing strength", "**Which paracetamol?**" in md and "`Paracetamol 650mg`" in md, True)
            check("prescription: no page token in output", "tok-x" in md, False)
            r = await client.call_tool("plan_prescription", {"medicines": [], "pincode": "110001"})
            check("prescription: empty list rejected by schema", r.is_error, True)
            r = await client.call_tool("search_medicine", {"query": "paracetamol", "pincode": "110001"})
            check("needs a strength: options, not an error", (r.is_error, text(r).startswith("## Which paracetamol?"),
                                                             "`Paracetamol 650mg`" in text(r)), (False, True, True))

            r = await client.call_tool("cache_stats", {})
            md = text(r)
            check("stats ok", (r.is_error, md.startswith("## PharmaWatch cache")), (False, True))
            stats = json.loads(text(await client.call_tool("cache_stats", {"response_format": "json"})))
            check("stats counts this session", stats["session"]["searches"] >= 3, True)

            r = await client.call_tool("cache_lab", {"query": "Dolo 500"})
            if stats["redis_ok"]:
                check("lab ok", (r.is_error, "Decision: **" in text(r)), (False, True))
                lab = json.loads(text(await client.call_tool("cache_lab", {"query": "Dolo 500", "response_format": "json"})))
                check("lab decision valid", lab["decision"] in ("exact_hit", "semantic_hit", "api_call"), True)
            else:
                check("lab without Redis is a tool error", r.is_error, True)
    finally:
        api.search_medicine_stream = real


async def part2_stdio(run: int):
    print(f"\nPart 2.{run}: real stdio subprocess (started from another directory)")
    params = StdioServerParameters(command=sys.executable, args=[os.path.join(ROOT, "mcp_server.py")],
                                   cwd=tempfile.gettempdir())
    junk = []  # anything on stdout that is not a protocol message reaches the client as an exception

    async def on_message(message):
        if isinstance(message, Exception):
            junk.append(message)

    async with Client(params, message_handler=on_message) as client:
        check("server name", client.server_info.name, "pharmawatch")
        check("instructions sent", "credits" in (client.instructions or ""), True)
        check("4 tools over stdio", len((await client.list_tools()).tools), 4)
        r = await client.call_tool("cache_lab", {"query": "Stamlo 5"})  # races the model warm-up
        lab_error = r.is_error
        r = await client.call_tool("cache_stats", {"response_format": "json"})
        stats = json.loads(text(r))
        check("stats over stdio", r.is_error, False)
        check("lab over stdio", lab_error, not stats["redis_ok"])
        check(".env found from another cwd", stats["serpapi_key_configured"], True)
        r = await client.call_tool("search_medicine", {"query": "Stamlo 5", "pincode": "000000"})
        check("bad PIN over stdio, 0 credits", r.is_error, True)
    check("stdout carried only protocol messages", junk, [])

    secrets = [v for k, v in os.environ.items() if k in ("SERP_API_KEY", "SERPAPI_API_KEY", "GEMINI_API_KEY") and v]
    check("no key in any output", any(s in json.dumps(stats) for s in secrets), False)


async def main():
    await part1_in_memory()
    for run in (1, 2, 3):  # startup races are timing-dependent
        await part2_stdio(run)


if __name__ == "__main__":
    anyio.run(main)
    print("\nALL PASSED" if all(results) else f"\n{results.count(False)} FAILED")
    sys.exit(0 if all(results) else 1)
