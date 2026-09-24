"""
comparator.py — Add delivery cost to every distilled listing and rank by final (landed) price.

Order: home-deliverable listings by landed cost → store-pickup-only → fee unknown → not deliverable.
"""

from typing import List

from pharmawatch.delivery_cost import calculate_delivery_cost, normalize_pincode

_STATUS_ORDER = {"free": 0, "charged": 0, "pickup_only": 1, "unknown": 2, "unserviceable": 3}


def rank_by_landed_price(
    distilled_results: List[dict],
    pincode,
    quantity: int = 1,
) -> List[dict]:
    """
    Return copies of distilled listings enriched with every calculate_delivery_cost()
    field (delivery_fee, platform_fee, total_landed_cost, delivery_status, delivery_label, …),
    sorted cheapest landed cost first, plus:
      - rank        : 1-based position
      - is_cheapest : True only for the cheapest listing that can be home-delivered
    Raises ValueError for an invalid PIN.
    """
    pin = normalize_pincode(pincode)
    ranked = []
    for item in distilled_results:
        row = dict(item)
        quote = calculate_delivery_cost(
            row.get("platform", ""), float(row.get("price_inr") or 0), pin, quantity=quantity
        )
        row.update(quote)
        row["pincode_zone"] = quote["zone"]
        ranked.append(row)

    ranked.sort(key=lambda r: (
        _STATUS_ORDER[r["delivery_status"]],
        r["total_landed_cost"] if r["total_landed_cost"] is not None else float("inf"),
        r.get("price_inr") or 0,
    ))

    for idx, row in enumerate(ranked, 1):
        row["rank"] = idx
        row["is_cheapest"] = False
    deliverable = [r for r in ranked if r["delivery_status"] in ("free", "charged")]
    if deliverable:
        deliverable[0]["is_cheapest"] = True
    return ranked
