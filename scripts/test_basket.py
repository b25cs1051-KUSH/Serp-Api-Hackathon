"""
test_basket.py — Offline checks for pharmawatch/basket.py (0 SerpApi credits).

Delivery rules are the real ones for PIN 110001: 1mg free from ₹100 (else ₹50), Chemist180 always
free, Netmeds free from ₹500 (else ₹29–39), Apollo free from ₹199 (else ₹80).

    python scripts/test_basket.py
"""

import itertools
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from pharmawatch import basket  # noqa: E402

PIN = "110001"
results = []


def check(name, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" (expected {expected!r})"))
    results.append(ok)


def offer(platform, cost, brand="Dolo 650", prescribed=True, packs=1, pack=15):
    return {"brand": brand, "platform": platform, "packs": packs, "pack_size": pack, "pack_estimated": False,
            "price_inr": cost / packs, "item_cost": cost, "per_tablet": round(cost / (packs * pack), 2),
            "prescribed": prescribed, "medicine_name": brand, "manufacturer": None,
            "direct_link": "", "search_link": "", "google_link": "", "page_token": ""}


def line(query, *offers, tablets=15):
    return {"query": query, "tablets": tablets, "tablets_how": "typed", "offers": list(offers)}


def stores(plan):
    return sorted((s["platform"], sorted(o["line"] for o in s["lines"])) for s in plan["stores"])


def brute_force(lines):
    """Every assignment of every kept offer (cheapest per pharmacy per line), no store cut."""
    fee = basket._fee_function(PIN)
    choices = []
    for ln in lines:
        ok = [o for o in ln["offers"] if fee(o["platform"], round(o["item_cost"], 2)) is not None]
        choices.append(basket._choices(ok, 99))
    best = None
    for a in itertools.product(*choices):
        p = basket._price(a, fee)
        if p is not None and (best is None or p[0] < best):
            best = p[0]
    return best


def run():
    # 1. Free-delivery threshold: both at 1mg (₹120, free from ₹100) beats the per-item cheapest split
    #    (A at Chemist180 ₹58 + B at 1mg ₹60 + ₹50 delivery = ₹168).
    r = basket.optimise([line("A", offer("Chemist180", 58), offer("1mg", 60)),
                         line("B", offer("Chemist180", 65), offer("1mg", 60))], PIN)
    best = r["with_swaps"]["best"]
    check("threshold: one 1mg order beats the split", (best["total"], stores(best)), (120.0, [("1mg", [0, 1])]))
    check("threshold: per-line cheapest alone is still reported",
          (r["per_line"][0]["cheapest_any"]["platform"], r["per_line"][1]["cheapest_any"]["platform"]),
          ("Chemist180", "Chemist180"))
    check("single store = the same 1mg order here", r["with_swaps"]["single_store"]["total"], 120.0)

    # 2. Split beats one store when no threshold helps: Chemist180 (free) for A, Chemist180 for B.
    r = basket.optimise([line("A", offer("Chemist180", 20), offer("Apollo Pharmacy", 15)),
                         line("B", offer("Chemist180", 30), offer("Apollo Pharmacy", 25))], PIN)
    check("small order: Chemist180 (free) beats Apollo (₹40 + ₹80 delivery)",
          (r["with_swaps"]["best"]["total"], stores(r["with_swaps"]["best"])), (50.0, [("Chemist180", [0, 1])]))
    check("fees reported", (r["with_swaps"]["best"]["fees_total"], r["with_swaps"]["best"]["items_total"]), (0.0, 50.0))

    # 3. Swapping to a same-composition generic saves money; as-prescribed keeps the brand.
    r = basket.optimise([line("Dolo 650", offer("Chemist180", 26.32), offer("Chemist180", 13.94, "Paracip 650", False))], PIN)
    check("with swaps picks the generic", r["with_swaps"]["best"]["stores"][0]["lines"][0]["brand"], "Paracip 650")
    check("as prescribed keeps the brand", r["as_prescribed"]["best"]["stores"][0]["lines"][0]["brand"], "Dolo 650")
    check("saving = difference", r["saving"], 12.38)

    # 3b. The prescribed brand of one line isn't sold: saving is compared on the other lines only.
    r = basket.optimise([line("Dolo 650", offer("Chemist180", 26.32), offer("Chemist180", 13.94, "Paracip 650", False)),
                         line("Atorbest 10", offer("Chemist180", 21.39, "Torvason 10", False))], PIN)
    check("saving over the lines both can cover", (r["saving"], r["saving_lines"]), (12.38, [0]))
    check("swap basket still covers every line", r["with_swaps"]["best"]["total"], 35.33)

    # 4. A line nobody sells is reported, the rest is still optimised.
    r = basket.optimise([line("A", offer("Chemist180", 20)), line("Nothing")], PIN)
    check("unavailable line reported", r["unavailable"], [1])
    check("rest still priced", r["with_swaps"]["best"]["total"], 20.0)

    # 5. A pharmacy without delivery rules can't be priced, so it is left out.
    r = basket.optimise([line("A", offer("RandomShop", 5), offer("Chemist180", 20))], PIN)
    check("unknown pharmacy excluded", stores(r["with_swaps"]["best"]), [("Chemist180", [0])])

    # 6. No single pharmacy has everything → single_store None, split still found.
    r = basket.optimise([line("A", offer("Chemist180", 20)), line("B", offer("1mg", 150))], PIN)
    check("no common pharmacy → no single-store plan", r["with_swaps"]["single_store"], None)
    check("split across two pharmacies", stores(r["with_swaps"]["best"]), [("1mg", [1]), ("Chemist180", [0])])

    # 7. Tablets: build_offers covers the count with whole packs (medicine unknown to the index).
    pooled = [{"medicine_name": "Zyxoltab 5 Tablet 10's", "platform": "Chemist180", "price_inr": 20.0,
               "delivery_status": "free", "total_landed_cost": 20.0}]
    o = basket.build_offers({"query": "Zyxoltab 5", "tablets": 15}, pooled, None)
    check("15 tablets from 10-packs = 2 packs", (o["tablets"], o["offers"][0]["packs"], o["offers"][0]["item_cost"]), (15, 2, 40.0))
    o = basket.build_offers({"query": "Zyxoltab 5", "tablets": None}, pooled, None)
    check("no count → one pack", (o["tablets"], o["tablets_how"], o["offers"][0]["packs"]), (10, "one pack", 1))

    # 8. The pruned search equals brute force on random baskets.
    rng = random.Random(7)
    platforms = ["1mg", "Chemist180", "Netmeds", "Apollo Pharmacy", "PharmEasy", "Truemeds", "Medplus"]
    mismatches = 0
    for _ in range(60):
        lines = []
        for li in range(rng.randint(1, 4)):
            offers = [offer(p, round(rng.uniform(10, 400), 2), f"B{li}", rng.random() < 0.5)
                      for p in rng.sample(platforms, rng.randint(1, 5))]
            lines.append(line(f"L{li}", *offers))
        got = basket.optimise(lines, PIN)["with_swaps"]["best"]
        want = brute_force(lines)
        if (got["total"] if got else None) != want:
            mismatches += 1
    check("pruned search = brute force (60 random baskets)", mismatches, 0)

    # 9. Many lines stay fast (search space capped).
    lines = [line(f"L{i}", *[offer(p, 50 + 7 * i + j) for j, p in enumerate(platforms)]) for i in range(8)]
    r = basket.optimise(lines, PIN)
    check("8 lines: combinations capped", r["stats"]["combinations"] <= 2 * basket.MAX_COMBINATIONS, True)
    check("8 lines: under 5 s", r["stats"]["ms"] < 5000, True)
    print(f"        (8 lines: {r['stats']['combinations']} combinations in {r['stats']['ms']} ms)")


if __name__ == "__main__":
    run()
    print("\nALL PASSED" if all(results) else f"\n{results.count(False)} FAILED")
    sys.exit(0 if all(results) else 1)
