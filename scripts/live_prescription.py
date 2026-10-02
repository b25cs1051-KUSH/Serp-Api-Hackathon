"""
live_prescription.py — run a whole prescription through the real pipeline and print the basket.
Uses SERP_API_KEY_2 (test key); without it, it stops unless ALLOW_MAIN_KEY=1. Cached searches cost 0.

    python scripts/live_prescription.py "Stamlo 5" "Dolo 650 x30" "Atorbest 10" "paracetamol"
    (append "xN" for a tablet count)
"""

import os
import re
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
elif os.getenv("ALLOW_MAIN_KEY") != "1":
    sys.exit("SERP_API_KEY_2 (test key) is not set. Live checks spend real credits; "
             "set ALLOW_MAIN_KEY=1 to use SERP_API_KEY instead.")
warnings.simplefilter("ignore")

from pharmawatch.prescription import prescription_stream  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402


def parse(arg):
    m = re.match(r"^(.*?)\s+x(\d+)$", arg.strip())
    return {"query": m.group(1), "tablets": int(m.group(2))} if m else {"query": arg.strip(), "tablets": None}


def show_plan(title, plan):
    if not plan:
        print(f"  {title}: none")
        return
    print(f"  {title}: ₹{plan['total']} (items ₹{plan['items_total']} + delivery ₹{plan['fees_total']})")
    for s in plan["stores"]:
        print(f"     {s['platform']:16} subtotal ₹{s['subtotal']:>8} + ₹{s['fee']} ({'free' if s['free_delivery'] else 'charged'})")
        for o in s["lines"]:
            tag = "" if o["prescribed"] else "  ← swap"
            print(f"        L{o['line'] + 1} {o['brand'][:18]:18} {o['packs']}×{o['pack_size']}{'~' if o['pack_estimated'] else ''}"
                  f" = ₹{o['item_cost']} (₹{o['per_tablet']}/tab){tag}")


def main(args):
    lines = [parse(a) for a in args]
    cache = _get_cache(verbose=False)
    before = len(cache.call_log)
    t = time.perf_counter()
    for name, payload in prescription_stream(lines, "110001", resolve_links=False, use_llm=False):
        at = time.perf_counter() - t
        if name == "line":
            extra = ""
            if payload["status"] == "choose":
                extra = str([o["query"] for o in payload["choose"]["options"]][:4])
            elif payload["status"] == "done":
                extra = f"{len(payload['listings'])} listings, {payload['offers']} offers, {payload['tablets']} tablets ({payload['tablets_how']})"
            elif payload["status"] == "main":
                extra = f"{len(payload['listings'])} listings"
            print(f"[{at:5.1f}s] line {payload['line'] + 1} {payload['query']!r}: {payload['status']} {extra}")
        elif name == "basket":
            print(f"[{at:5.1f}s] basket ({payload['stats']['combinations']} combinations, {payload['stats']['ms']} ms)")
            show_plan("CHEAPEST (with swaps)", payload["with_swaps"]["best"])
            show_plan("single pharmacy (with swaps)", payload["with_swaps"]["single_store"])
            show_plan("as prescribed", payload["as_prescribed"]["best"])
            print(f"  saving vs as prescribed: ₹{payload['saving']} | unavailable: {payload['unavailable']} | skipped: {payload['skipped']}")
    calls = cache.call_log[before:]
    print(f"\n{len(calls)} lookups, {sum(1 for c in calls if c['credit'])} credits, {time.perf_counter() - t:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
