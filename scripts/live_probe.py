"""
live_probe.py — try Google Shopping queries for a medicine and show which same-composition
brands each one surfaces, cheapest shelf price per tablet first. Spends 1 credit per uncached query.

Uses SERP_API_KEY_2 (test key); without it, it stops unless ALLOW_MAIN_KEY=1.

    python scripts/live_probe.py "Dolo 650" "Cipla Paracetamol 650mg" "Paracip 650"
    (first argument: the medicine whose composition is used; the rest: queries to run)
"""

import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
if os.getenv("SERP_API_KEY_2"):
    os.environ["SERP_API_KEY"] = os.environ["SERP_API_KEY_2"]
elif os.getenv("ALLOW_MAIN_KEY") != "1":
    sys.exit("SERP_API_KEY_2 (test key) is not set. Live checks spend real credits; "
             "set ALLOW_MAIN_KEY=1 to use SERP_API_KEY instead.")
warnings.simplefilter("ignore")

from pharmawatch.generics import _prepare, find_composition, group_matcher, ranked_listings  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402


def shelf_per_tab(row):
    return round(row["price_inr"] / row["pack_size"], 2) if row.get("pack_size") else None


def main(medicine, queries, pin="110001"):
    match = find_composition(medicine, use_llm=False)
    brand_of = group_matcher(match)
    cache = _get_cache(verbose=False)
    print(f"{medicine}: {match['entry']['name']} ({len(match['group'])} brands)")
    best_overall = []
    for q in queries:
        before = len(cache.call_log)
        rows = ranked_listings(q, pin, True)
        outcome = cache.call_log[before]["outcome"] if len(cache.call_log) > before else "?"
        by_brand = {}
        for r in rows:
            g = brand_of(r.get("medicine_name", ""))
            if g:
                by_brand.setdefault(g["brand"], (g, []))[1].append(r)
        offers = []
        for brand, (g, rs) in by_brand.items():
            for p in _prepare(rs, brand, False, match.get("strengths", ""), g["pack"]):
                offers.append((shelf_per_tab(p), p["platform"], brand, p["price_inr"], p["pack_size"], p["pack_estimated"]))
        offers = sorted(o for o in offers if o[0] is not None)
        best_overall += offers
        print(f"\n  query {q!r} [{outcome}]: {len(rows)} listings, {len(by_brand)} brands of the composition")
        for o in offers[:8]:
            print(f"     ₹{o[0]:>6}/tab  {o[2][:20]:20} {o[1][:14]:14} ₹{o[3]} / {o[4]}{'~' if o[5] else ''}")
    best_overall.sort()
    if best_overall:
        o = best_overall[0]
        print(f"\n  CHEAPEST SHELF PER TABLET: ₹{o[0]} — {o[2]} at {o[1]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
