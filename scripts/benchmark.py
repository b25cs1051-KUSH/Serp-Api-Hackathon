"""
benchmark.py — does PharmaWatch find a same-composition offer at least as cheap as the "cheaper
alternative" the pharmacies themselves suggest? Targets are shelf prices per tablet read off 1mg,
Chemist180 and Medplus product pages (Sept 2026).

Compared on the price per tablet *delivered* (the product ranks by it; Chemist180 ships free, so
its shelf price is its delivered price). Runs the real pipeline (links off). Uses SERP_API_KEY_2 when set, so demo credits stay untouched.
Everything already cached costs 0.

    python scripts/benchmark.py
"""

import os
import sys
import time
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
if os.getenv("SERP_API_KEY_2"):
    os.environ["SERP_API_KEY"] = os.environ["SERP_API_KEY_2"]
warnings.simplefilter("ignore")

from pharmawatch.pipeline import search_medicine_stream  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402

# medicine → (pharmacy's suggested alternative, its shelf price per tablet)
TARGETS = {
    "Dolo 650": ("Paracip 650 @ Chemist180 ₹13.94/10", 1.39),
    "Stamlo 5": ("Amlip 5 @ Chemist180 ₹13.48/10", 1.35),
    "Atorbest 10": ("Lipvas 10 @ Chemist180 ₹33.04/10", 3.30),
}


def shelf_per_tab(row):
    return round(row["price_inr"] / row["pack_size"], 2) if row.get("pack_size") else None


def best_offer(query, pin="110001"):
    result = dict(search_medicine_stream(query, pin, resolve_links=False, use_llm=False))
    alt = result.get("alternatives") or {}
    rows = list(alt.get("cheaper_alternatives") or []) + list(alt.get("other_alternatives") or [])
    if alt.get("reference"):
        rows.append(alt["reference"])
    offers = [(r["unit_landed_cost"], r["brand"], r["platform"], r["price_inr"], r["pack_size"], r["pack_estimated"],
               shelf_per_tab(r))
              for r in rows if r.get("unit_landed_cost") is not None]
    return min(offers) if offers else None, alt.get("suggested_alternatives", [])


def main():
    cache = _get_cache(verbose=False)
    ok_all = True
    for query, (target_desc, target) in TARGETS.items():
        before = len(cache.call_log)
        t = time.perf_counter()
        best, searched = best_offer(query)
        calls = cache.call_log[before:]
        spent = sum(1 for c in calls if c["credit"])
        ok = best is not None and best[0] <= target
        ok_all &= ok
        mark = "PASS" if ok else "FAIL"
        got = (f"₹{best[0]}/tab delivered (shelf ₹{best[6]}) {best[1]} @ {best[2]} (₹{best[3]}/{best[4]}{'~' if best[5] else ''})"
               if best else "nothing")
        print(f"  {mark}  {query:12} ours {got}  vs pharmacy {target_desc} = ₹{target}/tab"
              f"   [{spent} credits, {time.perf_counter() - t:.1f}s, extra searches {searched}]")
    print("\nALL PASSED" if ok_all else "\nSOME FAILED")
    return ok_all


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
