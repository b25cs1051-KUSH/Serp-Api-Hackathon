"""
prescription.py — a whole prescription, searched in parallel and bought as cheaply as possible.

    t=0  resolve every line in the medicine index (local)   "paracetamol" → ("line", choose): skipped
         ├─ main search, line 1 ─▶ ("line", main) ─▶ its 2 extra searches ─┐
         ├─ main search, line 2 ─▶ ("line", main) ─▶ its 2 extra searches ─┼─▶ per line: pool, compare,
         └─ main search, line 3 ─▶ ("line", main) ─▶ its 2 extra searches ─┘   offers ─▶ ("line", done)
                                                        all lines done ─▶ basket.optimise ─▶ ("basket", …)
                                    direct links only for the offers the basket picked ─▶ ("basket_links", …)

Every search of every line runs at the same time (one thread pool), so 5 medicines take about as
long as 1. A line's searches are the same as a single search (pipeline.py): main + generic salt +
the discounted-generic brand, then the same matching, pooling and comparison.
"""

import time
import warnings
from concurrent.futures import FIRST_COMPLETED, Future, wait
from typing import Any, Dict, Iterator, List, Tuple

from pharmawatch import basket
from pharmawatch.delivery_cost import normalize_pincode
from pharmawatch.generics import (
    allows_other_forms,
    assemble_alternatives,
    find_composition,
    main_listings,
    pick_candidates,
    pool_listings,
    ranked_listings,
)
from pharmawatch.pipeline import _POOL, _fetch_direct_link, _resolve, _tagged

MAX_LINES = 8


def prescription_stream(
    lines: List[dict],
    pincode,
    resolve_links: bool = False,
    use_llm: bool = True,
    verbose: bool = False,
) -> Iterator[Tuple[str, Any]]:
    """
    lines: [{"query": str, "tablets": int | None}]. Yields, as each is ready:
      ("line", {"line", "query", "status": "choose", "choose"})     needs a strength; left out of the basket
      ("line", {"line", "query", "status": "main", "listings"})     its main results
      ("line", {"line", "query", "status": "done", "listings", "alternatives", "tablets", "tablets_how",
                "offers": n})
      ("basket", basket.optimise(...) + "timings")
      ("basket_links", same, with direct_link on the chosen offers)   only when resolve_links
    Raises ValueError for an invalid PIN.
    """
    pin = normalize_pincode(pincode)
    t0 = time.perf_counter()

    def elapsed() -> int:
        return round((time.perf_counter() - t0) * 1000)

    state: Dict[int, dict] = {}
    futures: Dict[Future, Tuple[int, str]] = {}   # future → (line, kind: main | match | extra)

    for i, line in enumerate(lines[:MAX_LINES]):
        query = line["query"]
        res = _resolve(query)
        st = {"query": query, "tablets": line.get("tablets"), "match": None, "match_known": True,
              "main_raw": None, "extras": {}, "done": False, "skip": False}
        state[i] = st
        if res["kind"] == "ambiguous":
            st["skip"] = True
            yield "line", {"line": i, "query": query, "status": "choose",
                           "choose": {"query": query, "reason": res["reason"], "options": res["options"]}}
            continue
        search_q = query
        if res["kind"] in ("brand", "salt") and res.get("matched_by") == "fuzzy":
            search_q = res.get("brand") or res["label"]
        f = _POOL.submit(_tagged, f"line {i + 1} main: {query}", ranked_listings, search_q, pin,
                         res["kind"] == "brand", verbose, True)
        futures[f] = (i, "main")
        if res["kind"] == "candidates":
            st["match_known"] = False
            futures[_POOL.submit(find_composition, query, use_llm, res)] = (i, "match")
        elif res["kind"] in ("brand", "salt"):
            st["match"] = find_composition(query, use_llm, res)

    def main_list(st: dict, rows: List[dict]) -> List[dict]:
        m = st["match"]
        return main_listings(rows, st["query"], pin, allows_other_forms(st["query"], m["entry"] if m else None), m)

    pending = set(futures)
    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        for f in done:
            i, kind = futures[f]
            st = state[i]
            if kind == "main":
                try:
                    st["main_raw"] = f.result()
                except Exception as e:
                    warnings.warn(f"Main search failed for line {i + 1}: {e}")
                    st["main_raw"] = []
                yield "line", {"line": i, "query": st["query"], "status": "main", "listings": main_list(st, st["main_raw"])}
            elif kind == "match":
                try:
                    st["match"] = f.result()
                except Exception as e:
                    warnings.warn(f"Medicine lookup failed for line {i + 1}: {e}")
                st["match_known"] = True
            elif kind == "extra":
                pass

            # A line's extra searches start once its main results and medicine are known.
            if st["main_raw"] is not None and st["match_known"] and "started" not in st:
                st["started"] = True
                if st["match"]:
                    st["match"]["alternatives"] = pick_candidates(st["match"], st["main_raw"])
                    for q in st["match"]["alternatives"]:
                        g = _POOL.submit(_tagged, f"line {i + 1}: {q}", ranked_listings, q, pin, True, verbose)
                        futures[g] = (i, "extra")
                        st["extras"][q] = g
                        pending.add(g)

        # Lines whose searches are all in: pool, compare, build offers.
        for i, st in state.items():
            if st["skip"] or st["done"] or "started" not in st or not all(g.done() for g in st["extras"].values()):
                continue
            st["done"] = True
            extra_rows = []
            for q, g in st["extras"].items():
                if g.exception():
                    warnings.warn(f"Search '{q}' failed for line {i + 1}: {g.exception()}")
                else:
                    extra_rows.append(g.result())
            pooled = pool_listings(st["main_raw"], *extra_rows)
            listings = main_list(st, pooled)
            alternatives = assemble_alternatives(st["query"], st["match"], listings, pooled) if st["match"] else None
            offers = basket.build_offers({"query": st["query"], "tablets": st["tablets"]}, pooled, st["match"])
            st.update(listings=listings, offers=offers)
            yield "line", {"line": i, "query": st["query"], "status": "done", "listings": listings,
                           "alternatives": alternatives, "tablets": offers["tablets"],
                           "tablets_how": offers["tablets_how"], "offers": len(offers["offers"])}

    basket_lines = [{"query": st["query"], "tablets": st["offers"]["tablets"], "tablets_how": st["offers"]["tablets_how"],
                     "offers": st["offers"]["offers"], "line": i}
                    for i, st in state.items() if not st["skip"]]
    result = basket.optimise(basket_lines, pin)
    # optimise() numbers lines by position; map back to the prescription's own line numbers.
    ids = [ln["line"] for ln in basket_lines]
    _renumber(result, ids)
    result["skipped"] = [i for i, st in state.items() if st["skip"]]
    result["timings"] = {"basket_ms": elapsed()}
    yield "basket", result

    if resolve_links:
        chosen = [o for mode in ("with_swaps", "as_prescribed") for plan in (result[mode]["best"],) if plan
                  for s in plan["stores"] for o in s["lines"] if o.get("page_token") and not o.get("direct_link")]
        link_futures = {}
        for o in chosen:
            key = (o["platform"], o["medicine_name"], o["price_inr"])
            if key not in link_futures:
                link_futures[key] = _POOL.submit(_tagged, f"direct link (basket): {o['brand']} @ {o['platform']}",
                                                 _fetch_direct_link, {"page_token": o["page_token"], "platform": o["platform"],
                                                                      "brand": o["brand"], "medicine_name": o["medicine_name"]})
        wait(list(link_futures.values()))
        for o in chosen:
            f = link_futures[(o["platform"], o["medicine_name"], o["price_inr"])]
            if not f.exception() and f.result():
                o["direct_link"] = f.result()
        result["timings"]["basket_links_ms"] = elapsed()
        yield "basket_links", result


def _renumber(result: dict, ids: List[int]) -> None:
    """optimise() numbers lines 0..n-1 in the order given; use the prescription's line numbers."""
    for mode in ("with_swaps", "as_prescribed"):
        for plan in (result[mode]["best"], result[mode]["single_store"]):
            if plan:
                for s in plan["stores"]:
                    for o in s["lines"]:
                        o["line"] = ids[o["line"]]
        result[mode]["lines"] = [ids[i] for i in result[mode]["lines"]]
    for p in result["per_line"]:
        p["line"] = ids[p["line"]]
    result["unavailable"] = [ids[i] for i in result["unavailable"]]


def search_prescription(lines: List[dict], pincode, **kwargs) -> dict:
    """Non-streaming form: {"lines": {i: last line event}, "basket": ..., "basket_links"?: ...}."""
    out: Dict[str, Any] = {"lines": {}}
    for name, payload in prescription_stream(lines, pincode, **kwargs):
        if name == "line":
            out["lines"][payload["line"]] = payload
        else:
            out[name] = payload
    return out
