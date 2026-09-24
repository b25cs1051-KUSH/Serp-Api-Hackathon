"""
pipeline.py — One user search, run in parallel, results streamed as they're ready.

    t=0 ┬─ main search "Stamlo 5" ─▶ ("main", only real Stamlo 5 listings) ─▶ direct links of top 5 ─┐
        └─ Gemini: 3 substitutes ─┬─ search "Amlokind 5"  ─┐                                          │
                                  ├─ search "Amtas 5"     ─┼─▶ pool all 4 searches                    │
                                  └─ search "Amlopres 5"  ─┘   ├▶ ("main_update", main list + Stamlo 5 │
                                                               │   listings found in substitute       │
                                                               │   searches) — only if it grew        │
                                                               └▶ compare → direct links of cheaper   │
                                                                  alternatives ─▶ ("alternatives", …) │
                                              final top 5 all have their links ─▶ ("main_links", …) ◀┘

Events arrive in whatever order they finish; "alternatives" never waits for the main direct links.

Main list: only listings whose title is the searched medicine (the user's words, then Gemini's
catalogue name once known) — look-alikes such as Esta 5, Stalopam 5 or Stamlo Bis are dropped.

Pooling: a brand's own Google Shopping search often doesn't return that brand (Dolo 650, Amlopres 5),
while another search in the same run does. Every brand is therefore matched against the listings
of all searches in the run.

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
    pool_listings,
    ranked_listings,
)
from pharmawatch.search import get_direct_merchant_link
from serpapi_cache import call_tag

MAIN_DIRECT_LINKS = 5

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


def search_medicine_stream(
    query: str,
    pincode,
    resolve_links: bool = True,
    use_llm: bool = True,
    verbose: bool = False,
) -> Iterator[Tuple[str, Any]]:
    """
    Yields, as each is ready (order varies):
      ("main", listings)        — only listings that are the searched medicine, ranked by landed
                                  price; direct_link '' until "main_links"
      ("main_update", listings) — the final main list when pooling found more listings of the
                                  searched medicine in the substitute searches (omitted otherwise)
      ("alternatives", result)  — generics.assemble_alternatives() dict plus "timings", or None when
                                  the medicine isn't in compositions.md
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

    main_future = _POOL.submit(_tagged, "main search", ranked_listings, query, pin, False, verbose)
    match_future = _POOL.submit(find_composition, query, use_llm)
    alt_futures: Dict[str, Future] = {}

    main_raw: Optional[List[dict]] = None
    main_rows: List[dict] = []
    match, match_known = None, False
    pooled_done = False
    alt_result, alt_linked = None, []
    sent_alternatives, sent_main_links = False, not resolve_links

    pending = {main_future, match_future}
    while not (sent_alternatives and sent_main_links):
        if pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
        else:
            done = set()

        for future in done:
            if future is main_future:
                main_raw = future.result()
                main_rows = main_listings(main_raw, query, pin, allows_other_forms(query))
                links.fill(main_rows, [])
                timings["main_ms"] = elapsed()
                yield "main", main_rows
                pending |= set(links.request(main_rows[:MAIN_DIRECT_LINKS], "direct link (main)"))
            elif future is match_future:
                try:
                    match = future.result()
                except Exception as e:
                    warnings.warn(f"Composition lookup failed: {e}")
                    match = None
                match_known = True
                timings["gemini_ms"] = elapsed()
                if match:
                    # Substitutes start the moment Gemini answers, even while the main search runs.
                    alt_futures = {
                        brand: _POOL.submit(_tagged, f"substitute search: {brand}",
                                            ranked_listings, brand, pin, True, verbose)
                        for brand in match["alternatives"]
                    }
                    pending |= set(alt_futures.values())

        # ── Pool every search once main + all substitutes are in ──────────────
        if (not pooled_done and main_raw is not None and match_known
                and all(f.done() for f in alt_futures.values())):
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

                searched = match["matched_brand"] or query
                final_main = main_listings(pooled, searched, pin, allows_other_forms(query, match["entry"]))
                if [listing_key(r) for r in final_main] != [listing_key(r) for r in main_rows]:
                    main_rows = final_main
                    links.fill(main_rows, [])
                    yield "main_update", main_rows
                    pending |= set(links.request(main_rows[:MAIN_DIRECT_LINKS], "direct link (main)"))

                alt_result = assemble_alternatives(query, match, main_rows, pooled)
                alt_linked = alt_result["cheaper_alternatives"]
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
