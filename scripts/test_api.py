"""
test_api.py — Offline checks for api/main.py (0 SerpApi credits, no Gemini).

The pipeline is replaced by a stub that emits the real event sequence and writes to the real
cache call log; everything else (FastAPI app, validation, slots, SSE, Redis reads) is real.

    python scripts/test_api.py
"""

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402

CACHE = _get_cache(verbose=False)
calls_made = []


def check(name, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" (expected {expected!r})"))
    return ok


def listing(title, price, token="tok-123"):
    return {"platform": "Chemist180", "medicine_name": title, "price_inr": price, "total_landed_cost": price,
            "delivery_status": "free", "direct_link": "", "page_token": token}


def log_call(tag, outcome, credit):
    now = time.perf_counter()
    with CACHE._log_lock:
        CACHE.call_log.append({"start": now, "end": now + 0.004, "engine": "google_shopping",
                               "query": tag, "outcome": outcome, "credit": credit, "tag": tag})


def stub_pipeline(delay=0.0, fail=False):
    def fake(query, pincode, resolve_links=True, use_llm=True, verbose=False):
        calls_made.append((query, pincode))
        log_call("main search", "api_call", True)
        yield "main", [listing("Stamlo 5MG Tablet", 66.02)]
        if fail:
            raise RuntimeError("SerpApi exploded")
        time.sleep(delay)
        log_call("substitute search: Amlokind 5", "exact_hit", False)
        log_call("substitute search: Amtas 5", "semantic_hit (0.912)", False)
        alt = {"reference": listing("Stamlo 5MG Tablet", 66.02), "cheaper_alternatives": [listing("Amlokind 5MG Tablet", 19.41)],
               "other_alternatives": [], "not_found": ["Amtas 5"], "suggested_alternatives": ["Amlokind 5", "Amtas 5"]}
        yield "alternatives", alt
        yield "main_links", [dict(listing("Stamlo 5MG Tablet", 66.02), direct_link="https://chemist180.com/x")]
    return fake


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


def wait_idle(timeout=5):
    end = time.time() + timeout
    while api._running["pipelines"] and time.time() < end:
        time.sleep(0.05)
    return api._running["pipelines"]


def run_checks() -> bool:
    client = TestClient(api.app)   # no `with`: skips the lifespan warm-up (model not needed here)
    real_pipeline = api.search_medicine_stream
    results = []
    try:
        # ── health: shape, and keys never leave the server ───────────────
        r = client.get("/api/health")
        body = r.text
        secrets = [v for v in (os.getenv("SERP_API_KEY"), os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_KEY")) if v]
        results += [
            check("health 200", r.status_code, 200),
            check("health new fields", all(k in r.json() for k in ("active_searches", "max_concurrent_searches", "search_timeout_s")), True),
            check("health never contains a key", any(s in body for s in secrets), False),
        ]

        # ── stream: happy path ────────────────────────────────────────────
        api.search_medicine_stream = stub_pipeline()
        events = parse_sse(client.get("/api/search/stream", params={"q": "  Stamlo   5 ", "pincode": "110 001"}).text)
        names = [n for n, _ in events]
        data = dict((n, d) for n, d in events)
        call_events = [d for n, d in events if n == "call"]
        results += [
            check("stream: event order", [n for n in names if n != "call"], ["start", "main", "alternatives", "main_links", "done"]),
            check("stream: query cleaned, PIN normalised", (data["start"]["query"], data["start"]["pincode"]), ("Stamlo 5", "110001")),
            check("stream: every call reported", [c["kind"] for c in call_events], ["api", "exact", "semantic"]),
            check("stream: call payload fields", sorted(call_events[0]),
                  sorted(["n", "tag", "engine", "query", "kind", "similarity", "start_ms", "ms", "credit"])),
            check("stream: semantic similarity parsed", call_events[2]["similarity"], 0.912),
            check("stream: listings payload", sorted(data["main"]), ["at_ms", "listings"]),
            check("stream: page_token never sent", "page_token" in json.dumps(events), False),
            check("stream: done summary", (data["done"]["calls"], data["done"]["credits_spent"], data["done"]["credits_saved"]), (3, 1, 2)),
            check("stream: done payload fields", sorted(data["done"]),
                  sorted(["total_ms", "calls", "credits_spent", "credits_saved", "exact_hits", "semantic_hits", "est_time_saved_ms", "timings"])),
            check("stream: slot released", wait_idle(), 0),
        ]

        # ── JSON endpoint: happy path ─────────────────────────────────────
        r = client.get("/api/search", params={"q": "Stamlo 5", "pincode": "110001"})
        j = r.json()
        results += [
            check("json: 200", r.status_code, 200),
            check("json: final listings are main_links", j["listings"][0]["direct_link"], "https://chemist180.com/x"),
            check("json: alternatives", j["alternatives"]["cheaper_alternatives"][0]["medicine_name"], "Amlokind 5MG Tablet"),
            check("json: stages", [s["name"] for s in j["stages"]], ["main", "alternatives", "main_links"]),
            check("json: calls + summary", (len(j["calls"]), j["summary"]["credits_spent"], j["error"]), (3, 1, None)),
        ]

        # ── a search that needs a strength: options, then done, nothing spent ──
        def choose_stub(query, pincode, resolve_links=True, use_llm=True, verbose=False):
            yield "choose", {"query": query, "reason": "strength not given",
                             "options": [{"label": "Paracetamol 650mg tablet", "query": "Paracetamol 650mg", "comp_key": "k"}]}
        api.search_medicine_stream = choose_stub
        events = parse_sse(client.get("/api/search/stream", params={"q": "paracetamol", "pincode": "110001"}).text)
        choose = dict(events).get("choose", {})
        j = client.get("/api/search", params={"q": "paracetamol", "pincode": "110001"}).json()
        results += [
            check("choose: event order", [n for n, _ in events if n != "call"], ["start", "choose", "done"]),
            check("choose: options sent", [o["query"] for o in choose.get("options", [])], ["Paracetamol 650mg"]),
            check("choose: no credit", dict(events)["done"]["credits_spent"], 0),
            check("json: choose field", (j["choose"]["options"][0]["query"], j["listings"]), ("Paracetamol 650mg", None)),
        ]

        # ── bad input is refused before anything runs (0 credits) ─────────
        before = len(calls_made)
        bad_pin = parse_sse(client.get("/api/search/stream", params={"q": "Stamlo 5", "pincode": "01234"}).text)
        blank = parse_sse(client.get("/api/search/stream", params={"q": "   ", "pincode": "110001"}).text)
        digits = client.get("/api/search", params={"q": "12345", "pincode": "110001"})
        long_q = client.get("/api/search", params={"q": "x" * 200, "pincode": "110001"})
        results += [
            check("stream: bad PIN → error + done", [(n, d.get("code")) for n, d in bad_pin], [("error", "invalid_pincode"), ("done", None)]),
            check("stream: blank query → invalid_query", bad_pin and blank[0][1]["code"], "invalid_query"),
            check("json: digits-only query → 422", (digits.status_code, digits.json()["detail"]["code"]), (422, "invalid_query")),
            check("json: over-long query → 422 (not a framework error)", (long_q.status_code, long_q.json()["detail"]["code"]), (422, "invalid_query")),
            check("refused searches never reached the pipeline", len(calls_made), before),
        ]

        # ── busy: every slot taken ────────────────────────────────────────
        for _ in range(api.MAX_CONCURRENT_SEARCHES):
            api._slots.acquire()
        try:
            busy_json = client.get("/api/search", params={"q": "Stamlo 5", "pincode": "110001"})
            busy_sse = parse_sse(client.get("/api/search/stream", params={"q": "Stamlo 5", "pincode": "110001"}).text)
        finally:
            for _ in range(api.MAX_CONCURRENT_SEARCHES):
                api._slots.release()
        results += [
            check("json: busy → 429", (busy_json.status_code, busy_json.json()["detail"]["code"]), (429, "busy")),
            check("stream: busy → error event", busy_sse[0][1]["code"], "busy"),
        ]

        # ── deadline: partial results + 504, slot held until the pipeline ends ──
        api.search_medicine_stream = stub_pipeline(delay=1.5)
        real_timeout, api.SEARCH_TIMEOUT_S = api.SEARCH_TIMEOUT_S, 0.5
        try:
            r = client.get("/api/search", params={"q": "Stamlo 5", "pincode": "110001"})
            slot_held_after_timeout = api._running["pipelines"]
        finally:
            api.SEARCH_TIMEOUT_S = real_timeout
        results += [
            check("json: deadline → 504 with partial listings",
                  (r.status_code, r.json()["error"]["code"], len(r.json()["listings"])), (504, "timeout", 1)),
            check("slot held while the pipeline still runs", slot_held_after_timeout, 1),
            check("slot released when it ends", wait_idle(), 0),
        ]

        # ── pipeline failure: partial results + 502 ───────────────────────
        api.search_medicine_stream = stub_pipeline(fail=True)
        r = client.get("/api/search", params={"q": "Stamlo 5", "pincode": "110001"})
        results += [
            check("json: pipeline error → 502 with partial listings",
                  (r.status_code, r.json()["error"]["code"], len(r.json()["listings"])), (502, "pipeline_error", 1)),
            check("error message kept", "SerpApi exploded" in r.json()["error"]["message"], True),
            check("slot released after failure", wait_idle(), 0),
        ]

        # ── call log: trimmed, but never under a live reader ──────────────
        time.sleep(1.6)   # let the timed-out stub finish writing its calls
        api._prune_call_log(CACHE)
        results.append(check("call log empty when nobody is reading", len(CACHE.call_log), 0))
        reader_t0 = time.perf_counter()
        api._readers[-1] = reader_t0
        log_call("live search", "api_call", True)
        api._prune_call_log(CACHE)
        results.append(check("entry a live stream needs survives pruning", [e["tag"] for e in CACHE.call_log], ["live search"]))
        del api._readers[-1]
        api._prune_call_log(CACHE)

        # ── two streams at once: each gets its own events ─────────────────
        api.search_medicine_stream = stub_pipeline(delay=0.3)
        outs = {}

        def stream(q):
            outs[q] = parse_sse(client.get("/api/search/stream", params={"q": q, "pincode": "110001"}).text)

        threads = [threading.Thread(target=stream, args=(q,)) for q in ("Stamlo 5", "Telma 40")]
        [t.start() for t in threads]
        [t.join() for t in threads]
        results += [
            check("concurrent: both complete", sorted(outs[q][-1][0] for q in outs), ["done", "done"]),
            check("concurrent: each sees its own start", sorted(outs[q][0][1]["query"] for q in outs), ["Stamlo 5", "Telma 40"]),
            check("concurrent: slots released", wait_idle(), 0),
        ]

        # ── untouched read-only endpoints still answer ────────────────────
        s = client.get("/api/stats").json()
        e = client.get("/api/cache/entries")
        results += [
            check("stats: session fields", all(k in s["session"] for k in ("searches", "credits_spent", "credits_saved", "hit_rate_pct")), True),
            check("cache entries 200", e.status_code, 200),
        ]
    finally:
        api.search_medicine_stream = real_pipeline
    return all(results)


if __name__ == "__main__":
    passed = run_checks()
    print("\nALL PASSED" if passed else "\nSOME CHECKS FAILED")
    sys.exit(0 if passed else 1)
