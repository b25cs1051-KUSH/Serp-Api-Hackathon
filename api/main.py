"""
api/main.py — HTTP layer for the PharmaWatch UI.

A thin wrapper: every medicine / cache decision is made by pharmawatch/ and serpapi_cache/.
This module only exposes them over HTTP and makes the cache observable:

  GET /api/health          Redis, embedding model, which keys are configured (never the keys)
  GET /api/account         SerpApi plan usage (account.json, costs no credits)
  GET /api/search/stream   one medicine search as Server-Sent Events: pipeline stages as they
                           finish + every SerpApi call live (exact / semantic / API call, ms)
  GET /api/search          the same search as one JSON response (422 bad input, 429 busy,
                           504 deadline, 502 pipeline error)
  GET /api/cache/lab       "what would the cache do with this query?" — nearest cached
                           queries, cosine scores, dosage guard. 0 credits, read-only
  GET /api/cache/entries   what is in Redis right now, with TTLs
  GET /api/stats           cache counters + totals for this API process

Guards (each search can spend up to 12 SerpApi credits):
  - PIN and query are validated before anything runs — a bad request costs nothing
  - at most MAX_CONCURRENT_SEARCHES (default 4) searches run at once; more are refused
  - SEARCH_TIMEOUT_S (default 90) caps how long a request waits for a search
  - the shared SerpApi call log is trimmed once no running search can still need an entry

Run from the repo root:
    uvicorn api.main:app --port 8000
"""

import sys

# serpapi_cache prints emoji; on a Windows console / redirected log the default codepage can't
# encode them, RedisBackend's "connected" print raises, and the cache silently falls back to
# passthrough (every search costs a credit). UTF-8 output must be set before anything prints.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import json
import logging
import os
import queue
import re
import threading
import time
import urllib.request
from contextlib import asynccontextmanager
from typing import Iterator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from pharmawatch.delivery_cost import normalize_pincode
from pharmawatch.pipeline import search_medicine_stream
from pharmawatch.search import SHOPPING_PARAMS, _get_cache, warm_up
from serpapi_cache.backends import RedisBackend

load_dotenv()

# Cache internals used by the lab endpoint. If serpapi_cache renames them, only the lab is disabled.
try:
    from serpapi_cache.cache import _cache_params, _cosine_similarity, _dosage_guard_fires, _params_signature
    _LAB_AVAILABLE = True
except ImportError:
    _LAB_AVAILABLE = False

# Same params as pharmawatch.search.search_prices, so the lab predicts what a search would do.
_SHOPPING_PARAMS = SHOPPING_PARAMS
_DEFAULT_MISS_MS = 7000  # used for "time saved" until this process has timed a real API call

MAX_CONCURRENT_SEARCHES = int(os.getenv("MAX_CONCURRENT_SEARCHES", "4"))
SEARCH_TIMEOUT_S = float(os.getenv("SEARCH_TIMEOUT_S", "90"))
_QUERY_MIN, _QUERY_MAX = 2, 120

log = logging.getLogger("pharmawatch.api")
if not log.handlers:  # uvicorn configures its own loggers only; make ours visible too
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)

# A slot is held while a search's pipeline runs — even after its client disconnected or timed
# out, since it is still spending credits. Streams register while they read the call log.
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_SEARCHES)
_running_lock = threading.Lock()
_running = {"pipelines": 0}
_readers: dict[int, float] = {}   # id(stream) → its t0 (perf_counter)

_state = {"warm": "pending", "warm_ms": None, "warm_error": None}
_session_lock = threading.Lock()
_session = {"searches": 0, "calls": 0, "api_calls": 0, "exact_hits": 0, "semantic_hits": 0,
            "hit_ms_total": 0.0, "miss_ms_total": 0.0}


def _warm() -> None:
    _state["warm"] = "warming"
    try:
        _state["warm_ms"] = round(warm_up(verbose=False))
        _state["warm"] = "ready"
    except Exception as e:  # health endpoint reports it; searches still work (model loads lazily)
        _state["warm"], _state["warm_error"] = "failed", f"{type(e).__name__}: {e}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm, daemon=True, name="warm-up").start()  # ~40 s once, off the request path
    yield


app = FastAPI(title="PharmaWatch API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("UI_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _redis():
    """Raw Redis client (read-only use), or None when Redis is down."""
    backend = _get_cache(verbose=False).backend
    return getattr(backend, "_r", None) if backend is not None else None


def _classify(outcome: str) -> tuple[str, Optional[float]]:
    """'semantic_hit (0.912)' → ('semantic', 0.912). Kinds: exact | semantic | api | passthrough."""
    if outcome.startswith("exact"):
        return "exact", None
    if outcome.startswith("semantic"):
        m = re.search(r"\(([\d.]+)\)", outcome)
        return "semantic", float(m.group(1)) if m else None
    return ("passthrough" if "passthrough" in outcome else "api"), None


def _entry_kind(query_text: str) -> str:
    if query_text.startswith("gemini-"):
        return "llm_decision"
    if "google_immersive_product" in query_text:
        return "product_link"
    return "shopping"


def _clean_rows(rows):
    """Listings without internal fields the browser doesn't need (page tokens are long)."""
    if isinstance(rows, list):
        return [{k: v for k, v in r.items() if k != "page_token"} for r in rows]
    return rows


def _clean_alternatives(result):
    if not result:
        return result
    out = dict(result)
    for key in ("cheaper_alternatives", "other_alternatives"):
        out[key] = _clean_rows(out.get(key) or [])
    if out.get("reference"):
        out["reference"] = _clean_rows([out["reference"]])[0]
    return out


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


# ─────────────────────────────────────────────
# Health / account / stats
# ─────────────────────────────────────────────

@app.get("/api/health")
def health():
    cache = _get_cache(verbose=False)
    r = _redis()
    redis_ok = False
    if r is not None:
        try:
            redis_ok = bool(r.ping())
        except Exception:
            redis_ok = False
    return {
        "redis": "up" if redis_ok else "down (passthrough: every search costs a credit)",
        "redis_ok": redis_ok,
        "model": _state["warm"],
        "model_warm_ms": _state["warm_ms"],
        "model_error": _state["warm_error"],
        "similarity_threshold": cache.threshold,
        "serpapi_key_configured": bool(os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_API_KEY")),
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY")),
        "lab_available": _LAB_AVAILABLE,
        "active_searches": _running["pipelines"],
        "max_concurrent_searches": MAX_CONCURRENT_SEARCHES,
        "search_timeout_s": SEARCH_TIMEOUT_S,
    }


_account_cache = {"at": 0.0, "data": None}


@app.get("/api/account")
def account():
    """SerpApi plan usage. account.json is free; cached 30 s. The key never leaves the server."""
    if _account_cache["data"] and time.time() - _account_cache["at"] < 30:
        return _account_cache["data"]
    key = os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_API_KEY")
    if not key:
        raise HTTPException(503, "SERP_API_KEY not configured")
    try:
        with urllib.request.urlopen(f"https://serpapi.com/account.json?api_key={key}", timeout=10) as resp:
            raw = json.load(resp)
    except Exception as e:
        raise HTTPException(502, f"SerpApi account lookup failed: {type(e).__name__}")  # no URL → no key in logs
    fields = ("plan_name", "searches_per_month", "this_month_usage", "plan_searches_left",
              "extra_credits", "total_searches_left", "last_hour_searches", "account_rate_limit_per_hour")
    data = {k: raw.get(k) for k in fields}
    _account_cache.update(at=time.time(), data=data)
    return data


@app.get("/api/stats")
def stats():
    cache_stats = _get_cache(verbose=False).get_stats()
    with _session_lock:
        s = dict(_session)
    hits = s["exact_hits"] + s["semantic_hits"]
    avg_miss = s["miss_ms_total"] / s["api_calls"] if s["api_calls"] else None
    avg_hit = s["hit_ms_total"] / hits if hits else None
    return {
        "cache": cache_stats,
        "session": {
            "searches": s["searches"],
            "serpapi_calls": s["calls"],
            "credits_spent": s["api_calls"],
            "credits_saved": hits,
            "exact_hits": s["exact_hits"],
            "semantic_hits": s["semantic_hits"],
            "hit_rate_pct": round(hits / s["calls"] * 100, 1) if s["calls"] else 0.0,
            "avg_api_ms": round(avg_miss) if avg_miss else None,
            "avg_hit_ms": round(avg_hit, 1) if avg_hit is not None else None,
            "time_saved_ms": round(hits * (avg_miss or _DEFAULT_MISS_MS)),
        },
    }


# ─────────────────────────────────────────────
# Search — validation, slots, one core used by the SSE stream and the JSON endpoint
# ─────────────────────────────────────────────

_EMPTY_DONE = {"total_ms": 0, "calls": 0, "credits_spent": 0, "credits_saved": 0, "exact_hits": 0,
               "semantic_hits": 0, "est_time_saved_ms": 0, "timings": {}}


class SearchRejected(Exception):
    """A search refused before it starts — nothing was spent."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _validate(q: str, pincode: str) -> tuple[str, str]:
    """Cleaned query + 6-digit PIN, or SearchRejected(422). Runs before any credit can be spent."""
    query = " ".join((q or "").split())
    if not _QUERY_MIN <= len(query) <= _QUERY_MAX or not re.search(r"[A-Za-z]", query):
        raise SearchRejected(422, "invalid_query",
                             f"Enter a medicine name ({_QUERY_MIN}–{_QUERY_MAX} characters, including letters).")
    try:
        pin = normalize_pincode(pincode)
    except ValueError as e:
        raise SearchRejected(422, "invalid_pincode", str(e))
    return query, pin


def _start_search(query: str, pin: str, links: bool, llm: bool) -> dict:
    """
    Claim a slot (or SearchRejected 429) and start the pipeline on its own thread right away.
    The thread releases the slot when the pipeline ends, even if nobody is reading any more.
    """
    if not _slots.acquire(blocking=False):
        raise SearchRejected(429, "busy", f"{MAX_CONCURRENT_SEARCHES} searches are already running. "
                                          "Try again in a few seconds.")
    with _running_lock:
        _running["pipelines"] += 1
    with _session_lock:
        _session["searches"] += 1

    handle = {"query": query, "pin": pin, "links": links, "llm": llm,
              "t0": time.perf_counter(), "stages": queue.Queue()}
    with _running_lock:
        _readers[id(handle)] = handle["t0"]

    def run():
        try:
            for name, payload in search_medicine_stream(query, pin, resolve_links=links, use_llm=llm):
                handle["stages"].put((name, payload))
            handle["stages"].put(("__done__", None))
        except Exception as e:
            handle["stages"].put(("__error__", f"{type(e).__name__}: {e}"))
        finally:
            with _running_lock:
                _running["pipelines"] -= 1
            _slots.release()

    threading.Thread(target=run, daemon=True, name=f"search:{query[:30]}").start()
    return handle


def _prune_call_log(cache) -> None:
    """
    Drop call-log entries older than every stream still reading it (all of them if none is).
    Entries a live stream can still show (start ≥ its t0) are never removed. Readers older than
    the deadline are stale (their request ended without cleanup) and no longer hold entries back.
    """
    now = time.perf_counter()
    with _running_lock:
        for key, t0 in list(_readers.items()):
            if now - t0 > SEARCH_TIMEOUT_S + 30:
                del _readers[key]
        cutoff = min(_readers.values(), default=now)
    with cache._log_lock:
        cache.call_log[:] = [e for e in cache.call_log if e["start"] >= cutoff]


def _search_events(handle: dict) -> Iterator[tuple[str, object]]:
    """
    One running search as (event, data) pairs — exactly the SSE events:
      start, call, choose, main | main_update | main_links, alternatives, error {message, code}, done
    Yields ("__tick__", None) while waiting so the SSE layer can send keep-alives.
    Calls made by another search running at the same time can also appear (shared cache log).
    """
    cache = _get_cache(verbose=False)
    t0 = handle["t0"]
    seen: set[int] = set()
    calls: list[dict] = []
    timings: dict = {}
    outcome = "ok"

    def new_calls() -> list[dict]:
        with cache._log_lock:
            fresh = [e for e in cache.call_log if id(e) not in seen and e["start"] >= t0]
        out = []
        for e in fresh:
            seen.add(id(e))
            kind, similarity = _classify(e["outcome"])
            ms = (e["end"] - e["start"]) * 1000
            call = {
                "n": len(calls) + 1,
                "tag": e.get("tag") or "search",
                "engine": e.get("engine", ""),
                "query": e.get("query", ""),
                "kind": kind,
                "similarity": similarity,
                "start_ms": round((e["start"] - t0) * 1000),
                "ms": round(ms, 1),
                "credit": bool(e.get("credit")),
            }
            calls.append(call)
            out.append(call)
            with _session_lock:
                _session["calls"] += 1
                if kind in ("api", "passthrough"):
                    _session["api_calls"] += 1
                    _session["miss_ms_total"] += ms
                else:
                    _session["exact_hits" if kind == "exact" else "semantic_hits"] += 1
                    _session["hit_ms_total"] += ms
        return out

    try:
        yield "start", {"query": handle["query"], "pincode": handle["pin"], "links": handle["links"], "llm": handle["llm"]}
        while True:
            try:
                name, payload = handle["stages"].get(timeout=0.1)
            except queue.Empty:
                name, payload = None, None

            for call in new_calls():
                yield "call", call

            if name is None:
                if time.perf_counter() - t0 > SEARCH_TIMEOUT_S:
                    outcome = "timeout"
                    yield "error", {"code": "timeout",
                                    "message": f"The search took longer than {SEARCH_TIMEOUT_S:.0f}s. Results so far are "
                                               "shown; anything already fetched is cached and will be instant next time."}
                    break
                yield "__tick__", None
                continue

            elapsed = round((time.perf_counter() - t0) * 1000)
            if name == "__error__":
                outcome = "pipeline_error"
                log.warning("search %r failed: %s", handle["query"], payload)
                yield "error", {"code": "pipeline_error", "message": payload}
                break
            if name == "__done__":
                break
            timings[f"{name}_ms"] = elapsed
            if name == "alternatives":
                yield name, {"at_ms": elapsed, "result": _clean_alternatives(payload)}
            elif name == "choose":
                yield name, {"at_ms": elapsed, **payload}
            else:
                yield name, {"at_ms": elapsed, "listings": _clean_rows(payload)}

        for call in new_calls():
            yield "call", call
        spent = sum(1 for c in calls if c["credit"])
        hits = [c for c in calls if c["kind"] in ("exact", "semantic")]
        with _session_lock:
            avg_miss = _session["miss_ms_total"] / _session["api_calls"] if _session["api_calls"] else None
        total_ms = round((time.perf_counter() - t0) * 1000)
        log.info("search q=%r pin=%s outcome=%s total_ms=%d calls=%d credits_spent=%d credits_saved=%d",
                 handle["query"], handle["pin"], outcome, total_ms, len(calls), spent, len(hits))
        yield "done", {
            "total_ms": total_ms,
            "calls": len(calls),
            "credits_spent": spent,
            "credits_saved": len(hits),
            "exact_hits": sum(1 for c in hits if c["kind"] == "exact"),
            "semantic_hits": sum(1 for c in hits if c["kind"] == "semantic"),
            "est_time_saved_ms": round(len(hits) * (avg_miss or _DEFAULT_MISS_MS)),
            "timings": timings,
        }
    finally:  # also runs when the client disconnects mid-stream
        with _running_lock:
            _readers.pop(id(handle), None)
        _prune_call_log(cache)


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_stream(handle: dict) -> Iterator[str]:
    last_ping = time.perf_counter()
    for name, data in _search_events(handle):
        if name == "__tick__":
            if time.perf_counter() - last_ping > 5:
                last_ping = time.perf_counter()
                yield ": keep-alive\n\n"
            continue
        yield _sse(name, data)


@app.get("/api/search/stream")
def search_stream(
    q: str = Query(..., max_length=500),
    pincode: str = Query("110001", max_length=20),
    links: bool = True,
    llm: bool = True,
):
    """
    Events (in arrival order):
      start        {query, pincode, links, llm}
      call         one SerpApi request: n, tag, engine, query, kind, similarity, start_ms, ms, credit
      main | main_update | main_links   {at_ms, listings} — ranked listings of the searched medicine
      choose       {at_ms, query, reason, options: [{label, query}]} — the search needs a strength first
                   ('paracetamol'); nothing else follows and no credit is spent
      alternatives {at_ms, result} — same-composition brands + savings (result null when the medicine
                   isn't in the medicine index)
      error        {message, code}: invalid_query | invalid_pincode | busy | timeout | pipeline_error
      done         per-search summary: calls, credits spent/saved, total_ms, timings
    A refused search (bad input, busy) still answers 200 with error + done, because EventSource
    cannot read an HTTP error body; GET /api/search uses real status codes.
    """
    try:
        query, pin = _validate(q, pincode)
        handle = _start_search(query, pin, links, llm)
    except SearchRejected as e:
        log.info("search refused (%s): q=%r pin=%r", e.code, q[:60], pincode)
        refused = [_sse("error", {"code": e.code, "message": e.message}), _sse("done", _EMPTY_DONE)]
        return StreamingResponse(iter(refused), media_type="text/event-stream", headers=_SSE_HEADERS)
    return StreamingResponse(_sse_stream(handle), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.get("/api/search")
def search_json(
    q: str = Query(..., max_length=500),
    pincode: str = Query("110001", max_length=20),
    links: bool = True,
    llm: bool = True,
):
    """
    The same search as one JSON response, once every stage is done:
      {query, pincode, listings (final main list), alternatives, choose (options when the search
       needs a strength, else null), stages [{name, at_ms}],
       calls [...], summary (the stream's done payload), error}
    422 invalid input · 429 too many searches · 504 deadline passed · 502 pipeline error
    (504/502 still carry whatever was found before the failure).
    """
    try:
        result = collect_search(q, pincode, links, llm)
    except SearchRejected as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.message})

    if result["error"]:
        status = 504 if result["error"]["code"] == "timeout" else 502
        return JSONResponse(result, status_code=status)
    return result


def collect_search(q: str, pincode: str, links: bool, llm: bool, on_event=None) -> dict:
    """
    Validate, run one search to the end and return the /api/search JSON body (JSON-safe).
    Raises SearchRejected before anything is spent. on_event(name, data), if given, sees every
    event as it arrives (used by the MCP server for progress). Shared by GET /api/search and MCP.
    """
    query, pin = _validate(q, pincode)
    handle = _start_search(query, pin, links, llm)

    result = {"query": query, "pincode": pin, "listings": None, "alternatives": None, "choose": None,
              "stages": [], "calls": [], "summary": None, "error": None}
    for name, data in _search_events(handle):
        if name == "__tick__":
            continue
        if on_event is not None:
            on_event(name, data)
        if name in ("main", "main_update", "main_links"):
            result["listings"] = data["listings"]
            result["stages"].append({"name": name, "at_ms": data["at_ms"]})
        elif name == "alternatives":
            result["alternatives"] = data["result"]
            result["stages"].append({"name": name, "at_ms": data["at_ms"]})
        elif name == "choose":
            result["choose"] = {k: v for k, v in data.items() if k != "at_ms"}
            result["stages"].append({"name": name, "at_ms": data["at_ms"]})
        elif name == "call":
            result["calls"].append(data)
        elif name == "error":
            result["error"] = data
        elif name == "done":
            result["summary"] = data
    return json.loads(json.dumps(result, default=str))


# ─────────────────────────────────────────────
# Cache lab + explorer (read-only, 0 credits)
# ─────────────────────────────────────────────

@app.get("/api/cache/lab")
def cache_lab(q: str = Query(..., min_length=1, max_length=120), top: int = Query(6, ge=1, le=20)):
    """
    What would the cache do if you searched `q` now? Mirrors SerpApiCache._search for a
    google_shopping price search: normalize → exact key → embed → best cosine → threshold →
    dosage guard. Reads Redis only; never calls SerpApi.
    """
    if not _LAB_AVAILABLE:
        raise HTTPException(503, "Cache internals changed — lab disabled")
    cache = _get_cache(verbose=False)
    r = _redis()
    if r is None:
        raise HTTPException(503, "Redis is down — nothing cached")

    params = {**_SHOPPING_PARAMS, "q": f"{q} price"}
    key_params = _cache_params(params)
    query_text = cache._params_to_query_string(key_params)
    key = cache._make_key(key_params)
    params_sig = _params_signature(key_params)

    t = time.perf_counter()
    exact = bool(r.exists(f"{RedisBackend.PREFIX}{key}:value"))
    exact_ms = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    embedding = cache._embed(query_text)
    embed_ms = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    keys = list(r.smembers(RedisBackend.INDEX_KEY))
    pipe = r.pipeline()
    for k in keys:
        pipe.get(f"{RedisBackend.PREFIX}{k}:embedding")
        pipe.get(f"{RedisBackend.PREFIX}{k}:query")
        pipe.get(f"{RedisBackend.PREFIX}{k}:params")
    raw = pipe.execute()
    candidates = []
    for i, k in enumerate(keys):
        emb, text, sig = raw[3 * i], raw[3 * i + 1] or "", raw[3 * i + 2]
        vec = json.loads(emb) if emb else []
        if not vec:
            continue  # token-only / LLM decision entries: exact-match only
        score = _cosine_similarity(embedding, vec)
        candidates.append({
            "query_text": text,
            "similarity": round(score, 4),
            "above_threshold": score >= cache.threshold,
            "dosage_guard_blocks": _dosage_guard_fires(query_text, text),
            "same_params": sig == params_sig,
        })
    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    scan_ms = (time.perf_counter() - t) * 1000

    # Same rule as SerpApiCache: only entries fetched with the same other params can be reused.
    best = next((c for c in candidates if c["same_params"]), None)
    closer_other = candidates[0] if candidates and not candidates[0]["same_params"] and candidates[0]["above_threshold"] else None
    if exact:
        decision, reason = "exact_hit", "Same normalized query is already cached — one Redis GET, no embedding"
    elif best is None or (closer_other and not best["above_threshold"]):
        decision, reason = "api_call", ("Closest cached query was fetched with different params (page, filter, "
                                        "language or json_restrictor), so it can't be reused" if closer_other
                                        else "Nothing comparable in the cache yet")
    elif not best["above_threshold"]:
        decision, reason = "api_call", f"Closest cached query scores {best['similarity']:.3f} < threshold {cache.threshold}"
    elif best["dosage_guard_blocks"]:
        decision, reason = "api_call", "Similar enough, but the numbers (dose) differ — dosage guard forces a fresh search"
    else:
        decision, reason = "semantic_hit", f"Served from '{best['query_text'].split(' | ')[0]}' (similarity {best['similarity']:.3f})"

    return {
        "input": q,
        "normalized_query": query_text,
        "cache_key": key,
        "threshold": cache.threshold,
        "decision": decision,
        "reason": reason,
        "credits": 1 if decision == "api_call" else 0,
        "compared_against": len(candidates),
        "timings_ms": {"exact_lookup": round(exact_ms, 2), "embed": round(embed_ms, 1), "scan": round(scan_ms, 1)},
        "nearest": candidates[:top],
    }


@app.get("/api/cache/entries")
def cache_entries():
    """Everything in Redis right now: query text, kind, seconds left, stored size."""
    r = _redis()
    if r is None:
        return {"redis_ok": False, "entries": [], "counts": {}}
    keys = list(r.smembers(RedisBackend.INDEX_KEY))
    pipe = r.pipeline()
    for k in keys:
        pipe.get(f"{RedisBackend.PREFIX}{k}:query")
        pipe.ttl(f"{RedisBackend.PREFIX}{k}:value")
        pipe.strlen(f"{RedisBackend.PREFIX}{k}:value")
    raw = pipe.execute()
    entries = []
    for i, k in enumerate(keys):
        text, ttl, size = raw[3 * i] or "", raw[3 * i + 1], raw[3 * i + 2]
        if ttl == -2:
            continue  # expired, index not yet cleaned
        entries.append({"key": k, "query_text": text, "kind": _entry_kind(text),
                        "ttl_s": ttl if ttl >= 0 else None, "bytes": size})
    entries.sort(key=lambda e: (e["kind"], -(e["ttl_s"] or 0)))
    counts: dict = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return {"redis_ok": True, "entries": entries, "counts": counts,
            "total_bytes": sum(e["bytes"] or 0 for e in entries)}
