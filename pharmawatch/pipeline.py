"""
pipeline.py — One user search, run in parallel, results streamed as they're ready.

    t=0  resolve "Stamlo 5" in the medicine index (local, ~1 ms): Amlodipine 5mg tablet, 281 brands
         ├─ "paracetamol" (no strength)? → ("choose", strengths) and stop: nothing is spent
         └─ main search "Stamlo 5" ─▶ ("main", only real Stamlo 5 listings) ─▶ direct links of top 5 ─┐
              └─ then one more search in the same salt: "Amlodipine 5mg" ─▶ pool ────────────┐       │
                 (for a salt search: the brand with the widest maker range)                   │       │
                                                                                              │       │
                  ├▶ ("main_update", main list + Stamlo 5 listings found in the other searches) ◀┤      │
                  └▶ every brand of the composition found anywhere → compare → direct links of  │      │
                     cheaper ones ─▶ ("alternatives", …)                                       ◀┘      │
                                              final top 5 all have their links ─▶ ("main_links", …) ◀─┘

Events arrive in whatever order they finish; "alternatives" never waits for the main direct links.

Main list: only listings whose title is the searched medicine. For a salt search ("Gliclazide 80mg")
that is any brand with exactly that composition (Glizid 80, Diamicron 80 ...), never a combination
such as Glizid-M. Look-alikes such as Esta 5, Stalopam 5 or Stamlo Bis are dropped.

Pooling: a brand's own Google Shopping search often doesn't return that brand (Dolo 650, Amlopres 5),
while another search in the same run does. Every listing of every search is checked against every
brand of the composition.

direct_link: filled only for the top MAIN_DIRECT_LINKS main listings and for cheaper alternatives
(1 google_immersive_product call each), and only with the listing's own pharmacy page. Every other
listing keeps direct_link "" (search_link and google_link remain as fallbacks).
"""

import time
import warnings
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Dict, Iterator, List, Optional, Tuple

from pharmawatch.delivery_cost import normalize_pincode
from pharmawatch.distiller import sanitize_link
from pharmawatch.generics import (
    allows_other_forms,
    assemble_alternatives,
    find_composition,
    listing_key,
    main_listings,
    pick_candidates,
    pool_listings,
    ranked_listings,
)
from pharmawatch.medicines import resolve
from pharmawatch.search import get_direct_merchant_link
from serpapi_cache import call_tag

MAIN_DIRECT_LINKS = 5
ALT_DIRECT_LINKS = 3   # cheapest alternatives that get their product page (1 credit each)

# main search + Gemini + 3 substitutes + direct links, with headroom for overlapping users.
_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="pharmawatch")


def _tagged(tag: str, fn, *args):
    with call_tag(tag):
        return fn(*args)


def _fetch_direct_link(row: dict) -> str:
    """The listing's own pharmacy product page, or '' if it can't be resolved."""
    link = get_direct_merchant_link(row["page_token"], target_platform=row.get("platform"), verbose=False)
    return sanitize_link(link) if link else ""


class _Links:
    """Direct-link lookups for this search, keyed by listing so each offer is resolved at most once."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.futures: Dict[Tuple, Future] = {}

    def request(self, rows: List[dict], label: str) -> List[Future]:
        if not self.enabled:
            return []
        for row in rows:
            key = listing_key(row)
            if row.get("page_token") and key not in self.futures:
                tag = f"{label}: {row.get('brand') or row.get('medicine_name', '')} @ {row.get('platform')}"
                self.futures[key] = _POOL.submit(_tagged, tag, _fetch_direct_link, row)
        return [self.futures[listing_key(r)] for r in rows if listing_key(r) in self.futures]

    def ready(self, rows: List[dict]) -> bool:
        return all(self.futures[listing_key(r)].done() for r in rows if listing_key(r) in self.futures)

    def fill(self, rows: List[dict], linked: List[dict]) -> None:
        """direct_link = resolved page for rows in `linked`, '' for everything else."""
        linked_keys = {listing_key(r) for r in linked}
        for row in rows:
            key = listing_key(row)
            future = self.futures.get(key) if key in linked_keys else None
            row["direct_link"] = ""
            if future is not None and future.done():
                if future.exception():
                    warnings.warn(f"Direct link lookup failed for {key}: {future.exception()}")
                else:
                    row["direct_link"] = future.result()

    def pending(self) -> set:
        return {f for f in self.futures.values() if not f.done()}


def _resolve(query: str) -> dict:
    """medicines.resolve(), or {"kind": "none"} if the medicine index can't be read."""
    try:
        return resolve(query)
    except Exception as e:  # a missing/corrupt index only loses substitutes, never the search
        warnings.warn(f"Medicine index unavailable: {e}")
        return {"kind": "none"}


def search_medicine_stream(
    query: str,
    pincode,
    resolve_links: bool = True,
    use_llm: bool = True,
    verbose: bool = False,
) -> Iterator[Tuple[str, Any]]:
    """
    Yields, as each is ready (order varies):
      ("choose", {query, reason, options})  — the search needs a strength or variant first
                                  ('paracetamol'); nothing else follows and no credit is spent
      ("main", listings)        — only listings that are the searched medicine (for a salt search:
                                  any brand of that composition), ranked by landed price;
                                  direct_link '' until "main_links"
      ("main_update", listings) — the final main list when pooling found more listings of the
                                  searched medicine in the substitute searches (omitted otherwise)
      ("alternatives", result)  — generics.assemble_alternatives() dict plus "timings", or None when
                                  the medicine isn't in the medicine index
      ("main_links", listings)  — the final main list with direct_link set on the top
                                  MAIN_DIRECT_LINKS (only when resolve_links)
    Raises ValueError for an invalid PIN. A failed substitute search only drops that substitute.
    """
    pin = normalize_pincode(pincode)
    t0 = time.perf_counter()
    timings: Dict[str, int] = {}
    links = _Links(resolve_links)

    def elapsed() -> int:
        return round((time.perf_counter() - t0) * 1000)

    resolution = _resolve(query)
    if resolution["kind"] == "ambiguous":
        yield "choose", {"query": query, "reason": resolution["reason"], "options": resolution["options"]}
        return

    # A corrected spelling is searched as the medicine's real name: Google has nothing for "januvai 50".
    search_q = query
    if resolution["kind"] in ("brand", "salt") and resolution.get("matched_by") == "fuzzy":
        search_q = resolution.get("brand") or resolution["label"]
    main_future = _POOL.submit(_tagged, "main search", ranked_listings, search_q, pin, False, verbose)
    match_future: Optional[Future] = None
    match, match_known = None, True
    if resolution["kind"] == "candidates":           # spelling with several fixes: Gemini picks, in parallel
        match_future = _POOL.submit(find_composition, query, use_llm, resolution)
        match_known = False
    elif resolution["kind"] in ("brand", "salt"):
        match = find_composition(query, use_llm, resolution)
        timings["match_ms"] = elapsed()

    alt_futures: Dict[str, Future] = {}
    main_raw: Optional[List[dict]] = None
    main_rows: List[dict] = []
    subs_started = pooled_done = False
    alt_result, alt_linked = None, []
    sent_alternatives, sent_main_links = False, not resolve_links

    def main_list(rows: List[dict]) -> List[dict]:
        return main_listings(rows, query, pin, allows_other_forms(query, match["entry"] if match else None), match)

    pending = {main_future} | ({match_future} if match_future else set())
    while not (sent_alternatives and sent_main_links):
        if pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
        else:
            done = set()

        for future in done:
            if future is main_future:
                main_raw = future.result()
                main_rows = main_list(main_raw)
                links.fill(main_rows, [])
                timings["main_ms"] = elapsed()
                yield "main", main_rows
                pending |= set(links.request(main_rows[:MAIN_DIRECT_LINKS], "direct link (main)"))
            elif future is match_future:
                try:
                    match = future.result()
                except Exception as e:
                    warnings.warn(f"Medicine lookup failed: {e}")
                    match = None
                match_known = True
                timings["match_ms"] = elapsed()
                if match and match["matched_by"] == "gemini":
                    timings["gemini_ms"] = timings["match_ms"]

        # ── Substitutes: once the main results and the medicine are known. Brands already in the
        #    main results are priced there, so the live searches go to brands not seen yet. ────────
        if not subs_started and main_raw is not None and match_known:
            subs_started = True
            if match:
                if not main_rows:
                    main_rows = main_list(main_raw)  # the match arrived after "main" (spelling fix)
                    if main_rows:
                        links.fill(main_rows, [])
                        yield "main_update", main_rows
                        pending |= set(links.request(main_rows[:MAIN_DIRECT_LINKS], "direct link (main)"))
                match["alternatives"] = pick_candidates(match, main_raw)
                alt_futures = {
                    q: _POOL.submit(_tagged, f"same-salt search: {q}", ranked_listings, q, pin, True, verbose)
                    for q in match["alternatives"]
                }
                pending |= set(alt_futures.values())

        # ── Pool every search once main + all substitutes are in ──────────────
        if not pooled_done and subs_started and all(f.done() for f in alt_futures.values()):
            pooled_done = True
            if match:
                alt_ranked = []
                for brand, future in alt_futures.items():
                    if future.exception():
                        warnings.warn(f"Search for substitute '{brand}' failed: {future.exception()}")
                    else:
                        alt_ranked.append(future.result())
                pooled = pool_listings(main_raw, *alt_ranked)
                timings["substitutes_ms"] = elapsed()

                final_main = main_list(pooled)
                if [listing_key(r) for r in final_main] != [listing_key(r) for r in main_rows]:
                    main_rows = final_main
                    links.fill(main_rows, [])
                    yield "main_update", main_rows
                    pending |= set(links.request(main_rows[:MAIN_DIRECT_LINKS], "direct link (main)"))

                alt_result = assemble_alternatives(query, match, main_rows, pooled)
                alt_linked = alt_result["cheaper_alternatives"][:ALT_DIRECT_LINKS]
                pending |= set(links.request(alt_linked, "direct link (cheaper alt)"))

        # ── Alternatives: as soon as their own links are done ──────────────────
        if pooled_done and not sent_alternatives and links.ready(alt_linked):
            sent_alternatives = True
            if alt_result is not None:
                links.fill(alt_result["cheaper_alternatives"] + alt_result["other_alternatives"], alt_linked)
                if alt_result["reference"] is not None:
                    links.fill([alt_result["reference"]], main_rows[:MAIN_DIRECT_LINKS])
                timings["alternatives_ms"] = elapsed()
                alt_result["timings"] = dict(timings)
            yield "alternatives", alt_result

        # ── Main links: once the main list is final and its top 5 are resolved ──
        top = main_rows[:MAIN_DIRECT_LINKS]
        if pooled_done and not sent_main_links and links.ready(top):
            sent_main_links = True
            links.fill(main_rows, top)
            timings["main_links_ms"] = elapsed()
            yield "main_links", main_rows

        if not pending and not (sent_alternatives and sent_main_links):
            pending = links.pending()
            if not pending and not done:
                raise RuntimeError("search_medicine_stream stalled")  # every branch above is terminal


def search_medicine(query: str, pincode, **kwargs) -> dict:
    """Non-streaming form: {"main", "main_update" (if any), "alternatives", "main_links" (if links)}."""
    return dict(search_medicine_stream(query, pincode, **kwargs))
