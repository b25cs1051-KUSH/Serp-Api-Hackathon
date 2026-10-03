"""
test_rules_integrity.py — Offline checks that notes/postal_codes_delivery_rules.json is internally sound
and reproduces every real checkout we have seen (0 SerpApi credits).

  1. Real carts: the amount to pay on PharmEasy / Apollo / Chemist180 / 1mg screenshots, to the rupee.
  2. Invariants for every platform × zone × order value ₹1–5,000: no negative fee, slab fees never rise
     with the order, landed = order + fee + platform fee, "free" only at/above the threshold,
     unserviceable stays unserviceable, every platform names its source.
  3. Every store the distiller recognises has delivery rules (none is silently unpriced).
  4. PIN and quantity edge cases.

    python scripts/test_rules_integrity.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from pharmawatch.delivery_cost import (  # noqa: E402
    calculate_delivery_cost as q,
    load_delivery_rules,
    lookup_zone,
    resolve_platform_key,
)
from pharmawatch.distiller import PLATFORM_NAME_PATTERNS  # noqa: E402

ZONE_PIN = {"metro": "110001", "tier2": "226001", "tier3": "250002", "remote": "781001", "unserviceable": "744101"}
results = []


def check(name, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" (expected {expected!r})"))
    results.append(ok)


def real_carts():
    print("\nReal carts (screenshots / checkout)")
    # (platform, selling price, PIN, amount to pay on the site, where it was seen)
    carts = [
        ("PharmEasy", round(174 * 0.93, 2), "250002", round(174 * 0.93, 2) + 130 + 13, "MRP ₹174 → ₹130 + ₹13"),
        ("PharmEasy", round(348 * 0.93, 2), "250002", round(348 * 0.93, 2) + 109 + 13, "MRP ₹348 → ₹109 + ₹13"),
        ("PharmEasy", round(522 * 0.93, 2), "250002", round(522 * 0.93, 2) + 49 + 13, "MRP ₹522 → ₹49 + ₹13"),
        ("PharmEasy", round(870 * 0.93, 2), "250002", round(870 * 0.93, 2) + 10 + 13, "MRP ₹870 → ₹10 + ₹13"),
        ("PharmEasy", round(1044 * 0.93, 2), "250002", round(1044 * 0.93, 2) + 0 + 13, "MRP ₹1,044 → free + ₹13"),
        ("Apollo", 80, "110001", 173.22, "₹80 cart → ₹173.22"),
        ("Apollo", 176, "110001", 269.22, "₹176 cart → ₹269.22"),
        ("Apollo", 264, "110001", 271.08, "₹264 cart → ₹271.08"),
        ("Chemist180", 26.32, "122001", 126.32, "₹26.32 → ₹100 delivery (Google product page + checkout)"),
        ("1mg", 28.30, "122001", 78.30, "Gurgaon checkout: ₹50 delivery"),
    ]
    for platform, price, pin, to_pay, note in carts:
        check(f"{platform} {note}", q(platform, price, pin)["total_landed_cost"], round(to_pay, 2))


def invariants():
    print("\nInvariants: every platform × zone × order value ₹1–5,000")
    rules = load_delivery_rules()
    values = [1, 10, 25, 49, 99, 100, 149, 150, 198.99, 199, 249, 250, 323, 348, 485, 499, 500, 749, 750, 809,
              849, 850, 929.99, 930, 999, 1000, 1299, 1300, 1999, 2000, 3999, 4000, 5000]
    bad = {"negative fee": [], "fee rises with order": [], "landed ≠ order + fees": [], "free below threshold": [],
           "unserviceable priced": [], "no source": []}
    for key, p in rules["platforms"].items():
        if not p.get("source"):
            bad["no source"].append(key)
        for zone, pin in ZONE_PIN.items():
            prev = None
            for v in values:
                r = q(p["display_name"], v, pin)
                if zone == "unserviceable":
                    if r["delivery_status"] != "unserviceable":
                        bad["unserviceable priced"].append((key, v))
                    continue
                fee = r["delivery_fee"]
                if fee is None:
                    continue
                if fee < 0:
                    bad["negative fee"].append((key, zone, v))
                if prev is not None and fee > prev + 1e-9:
                    bad["fee rises with order"].append((key, zone, v, prev, fee))
                prev = fee
                if r["total_landed_cost"] != round(v + fee + r["platform_fee"], 2):
                    bad["landed ≠ order + fees"].append((key, zone, v))
                thr = r["free_delivery_threshold"]
                if fee == 0 and thr and v < thr:
                    bad["free below threshold"].append((key, zone, v, thr))
    for name, found in bad.items():
        check(name, found[:5], [])


def coverage():
    print("\nEvery recognised store has delivery rules")
    unpriced = [name for _, name in PLATFORM_NAME_PATTERNS if resolve_platform_key(name) is None]
    check("distiller stores without rules", unpriced, [])
    for _, name in PLATFORM_NAME_PATTERNS:
        r = q(name, 100, "110001")
        if r["delivery_status"] == "unknown":
            print(f"        note: {name} has no published fee in metro ({r['delivery_label']})")


def pins_and_quantity():
    print("\nPIN and quantity edge cases")
    check("Andaman 744 beats remote 74", lookup_zone("744101")[0], "unserviceable")
    check("Leh 1941 beats remote 19", lookup_zone("194101")[0], "unserviceable")
    check("Unlisted prefix → default tier3, flagged", lookup_zone("250002"), ("tier3", True))
    check("Spaces inside the PIN", lookup_zone(" 110 001 ")[0], "metro")
    for bad_pin in ("000000", "012345", "12345", "1100011", "abcdef", "", None, "11000a"):
        try:
            lookup_zone(bad_pin)
            check(f"invalid PIN {bad_pin!r} rejected", "accepted", "ValueError")
        except ValueError:
            check(f"invalid PIN {bad_pin!r} rejected", "ValueError", "ValueError")
    check("quantity 0 counts as 1", q("1mg", 100, "110001", quantity=0)["order_value"], 100.0)
    check("negative quantity counts as 1", q("1mg", 100, "110001", quantity=-3)["order_value"], 100.0)
    check("quantity pushes order over threshold", q("1mg", 250, "110001", quantity=2)["delivery_status"], "free")
    check("unknown store never guessed", q("RandomShop", 100, "110001")["total_landed_cost"], None)
    check("empty store name never guessed", q("", 100, "110001")["total_landed_cost"], None)


if __name__ == "__main__":
    real_carts()
    invariants()
    coverage()
    pins_and_quantity()
    print("\nALL PASSED" if all(results) else f"\n{results.count(False)} FAILED")
    sys.exit(0 if all(results) else 1)
