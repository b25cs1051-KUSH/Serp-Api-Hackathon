"""
test_p4_delivery_cost.py — Offline checks for delivery_cost.py + comparator.py (0 SerpApi credits).

    python scripts/test_p4_delivery_cost.py            # run checks
    python scripts/test_p4_delivery_cost.py 744101     # also print every platform's quote for a PIN
"""

import sys

from pharmawatch.comparator import rank_by_landed_price
from pharmawatch.delivery_cost import (
    calculate_delivery_cost,
    load_delivery_rules,
    lookup_zone,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def check(name, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" (expected {expected!r})"))
    return ok


def run_checks() -> bool:
    q = calculate_delivery_cost
    results = [
        # Zones
        check("Delhi metro", lookup_zone("110001"), ("metro", False)),
        check("'38' in metro+tier3 → metro", lookup_zone("380001"), ("metro", False)),
        check("Andaman 744 beats remote 74", lookup_zone("744101"), ("unserviceable", False)),
        check("Unlisted prefix → default", lookup_zone("250001"), ("tier3", True)),
        check("Spaces allowed", lookup_zone("110 001"), ("metro", False)),
        # Threshold: free vs charged
        check("1mg metro ₹499 → ₹50", q("1mg", 499, "110001")["delivery_fee"], 50.0),
        check("1mg metro ₹500 → free", q("1mg", 500, "110001")["delivery_status"], "free"),
        check("1mg gap to free", q("1mg", 470, "110001")["amount_to_free_delivery"], 30.0),
        check("Quantity counts toward threshold", q("1mg", 250, "110001", quantity=2)["delivery_status"], "free"),
        check("Landed = qty×price + fee", q("1mg", 150, "400001", quantity=2)["total_landed_cost"], 350.0),
        check("Weight-based fee shown as estimate", q("eMedicalwala", 100, "110001")["delivery_label"],
              "~₹50 delivery (weight-based estimate) · add ₹200 more for FREE delivery"),
        # Slabs (Netmeds metro)
        check("Netmeds ₹200 → ₹59", q("Netmeds", 200, "110001")["delivery_fee"], 59.0),
        check("Netmeds ₹300 → ₹29", q("Netmeds", 300, "110001")["delivery_fee"], 29.0),
        check("Netmeds ₹500 → free", q("Netmeds", 500, "110001")["delivery_label"], "FREE delivery (order ≥ ₹500)"),
        check("Netmeds tier3 same slabs", q("Netmeds", 300, "250001")["delivery_fee"], 29.0),
        check("Magicine ₹4000 prepaid slab", q("Magicine Pharma", 4000, "110001")["delivery_label"],
              "₹69 delivery (prepaid only) · no free-delivery offer"),
        # Platform fee
        check("Truemeds ₹11 platform fee", q("Truemeds", 100, "110001")["total_landed_cost"], 160.0),
        # Always-free, pickup, unserviceable, unknown
        check("Chemist180 ₹100 below ₹1,000", q("Chemist180", 999, "110001")["delivery_fee"], 100.0),
        check("Chemist180 free from ₹1,000", q("Chemist180", 1000, "781001")["delivery_label"], "FREE delivery (order ≥ ₹1,000)"),
        check("SastaSundar ₹29 below ₹149", q("SastaSundar", 100, "700001")["delivery_fee"], 29.0),
        check("Medplus metro ₹0 fee", q("Medplus", 10, "110001")["delivery_label"], "FREE delivery on every order"),
        check("Medplus tier3 pickup only", q("Medplus", 100, "250001")["delivery_status"], "pickup_only"),
        check("Andaman unserviceable", q("1mg", 500, "744101")["total_landed_cost"], None),
        check("Kogland free delivery (Google)", q("Kogland", 100, "190001")["delivery_status"], "free"),
        check("Unknown store not guessed", q("RandomShop", 100, "110001")["delivery_fee"], None),
        check("Medivik tier2 typo fixed", q("Medivik", 100, "160001")["delivery_fee"], 45.0),
    ]

    try:
        q("1mg", 100, "01234")
        results.append(check("Invalid PIN raises", "no error", "ValueError"))
    except ValueError:
        results.append(check("Invalid PIN raises", "ValueError", "ValueError"))

    listings = [
        {"platform": "PharmEasy", "price_inr": 90.0},   # 90 + 75 = 165
        {"platform": "1mg", "price_inr": 120.0},        # 120 + 75 = 195
        {"platform": "Medplus", "price_inr": 10.0},     # pickup only in tier3
        {"platform": "RandomShop", "price_inr": 5.0},   # unknown
    ]
    ranked = rank_by_landed_price(listings, "250001")
    results.append(check("Ranking order", [r["platform"] for r in ranked],
                         ["PharmEasy", "1mg", "Medplus", "RandomShop"]))
    results.append(check("Cheapest flag", [r["is_cheapest"] for r in ranked], [True, False, False, False]))
    return all(results)


def print_pin_table(pin: str, price: float = 150.0):
    zone, assumed = lookup_zone(pin)
    print(f"\nEvery platform, ₹{price:.0f} order → PIN {pin} ({zone}{', assumed' if assumed else ''}):")
    for key, p in load_delivery_rules()["platforms"].items():
        r = calculate_delivery_cost(p["display_name"], price, pin)
        landed = f"₹{r['total_landed_cost']:.2f}" if r["total_landed_cost"] is not None else "—"
        print(f"  {p['display_name']:<18} {landed:>9}  {r['delivery_label']}  [{r['estimated_days']}]")


if __name__ == "__main__":
    passed = run_checks()
    for pin in sys.argv[1:]:
        print_pin_table(pin)
    print("\nALL PASSED" if passed else "\nSOME CHECKS FAILED")
    sys.exit(0 if passed else 1)
