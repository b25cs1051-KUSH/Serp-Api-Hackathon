"""
delivery_cost.py — PIN code → delivery zone → delivery fee → landed cost, per platform.

All numbers come from notes/postal_codes_delivery_rules.json. Nothing is invented:
if a platform or zone has no published fee, the quote says so (status "unknown")
instead of guessing a number.

Every quote carries a delivery_status so the UI can always tell the user what
delivery costs for this offer:
    free           — ₹0 delivery (always free, or order value ≥ free-delivery threshold)
    charged        — delivery fee is added to the price
    pickup_only    — no home delivery to this PIN, store pickup only (₹0)
    unserviceable  — platform does not deliver to this PIN
    unknown        — platform/zone has no published fee
"""

import json
import os
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

RULES_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "notes",
    "postal_codes_delivery_rules.json",
)

# When one prefix sits in several zones (e.g. "38" is listed under metro and tier3),
# the earlier zone here wins. Longer prefixes always beat shorter ones first.
ZONE_PRIORITY = ["unserviceable", "metro", "tier2", "remote", "tier3"]

# Fees for these fee_types depend on parcel weight, so the published fee is an estimate.
WEIGHT_FEE_TYPES = {"weight_and_value_based", "volumetric_weight_b2b"}
# estimated_fee: the store publishes its free-delivery threshold but not the fee below it.
ESTIMATED_FEE_TYPES = WEIGHT_FEE_TYPES | {"estimated_fee"}

# Substring (lowercase, alphanumerics only) of a distiller platform name → rules key.
PLATFORM_ALIASES: List[Tuple[str, str]] = [
    ("1mg", "tata_1mg"),
    ("pharmeasy", "pharmeasy"),
    ("apollo", "apollo_247"),
    ("netmeds", "netmeds"),
    ("truemeds", "truemeds"),
    ("medplus", "medplus_mart"),
    ("dawaadost", "dawaadost"),
    ("magicine", "magicine_pharma"),
    ("chemist180", "chemist180"),
    ("emedicalwala", "emedicalwala"),
    ("medivik", "medivik"),
    ("medizinhub", "medizinhub"),
    ("kogland", "kogland_commerce"),
    ("sastasundar", "sastasundar"),
]

_PIN_RE = re.compile(r"^[1-9]\d{5}$")


@lru_cache(maxsize=1)
def load_delivery_rules() -> dict:
    """Load delivery rules JSON once. Raises if the file is missing — never silently fakes fees."""
    with open(RULES_JSON_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _prefix_index() -> Dict[str, str]:
    """prefix → zone, with ZONE_PRIORITY deciding prefixes listed under several zones."""
    pin_zones = load_delivery_rules()["pin_zones"]
    index: Dict[str, str] = {}
    for zone in ZONE_PRIORITY:
        for prefix in pin_zones.get(zone, {}).get("prefixes", []):
            index.setdefault(str(prefix), zone)
    return index


def normalize_pincode(pincode) -> str:
    """Return a clean 6-digit Indian PIN or raise ValueError ("110 001" → "110001")."""
    pin = re.sub(r"\s", "", str(pincode or ""))
    if not _PIN_RE.match(pin):
        raise ValueError(f"Invalid PIN code {pincode!r}: expected 6 digits, not starting with 0")
    return pin


def lookup_zone(pincode) -> Tuple[str, bool]:
    """
    Return (zone, zone_assumed). Longest matching prefix wins, so "744101" (Andaman)
    is unserviceable even though "74" is remote. zone_assumed is True when no prefix
    matched and the rules' default zone was used.
    """
    pin = normalize_pincode(pincode)
    index = _prefix_index()
    for length in range(len(pin), 0, -1):
        zone = index.get(pin[:length])
        if zone:
            return zone, False
    return load_delivery_rules()["pin_zones"].get("default", "tier3"), True


def get_pincode_zone(pincode) -> str:
    """Delivery zone for a PIN: 'metro', 'tier2', 'tier3', 'remote' or 'unserviceable'."""
    return lookup_zone(pincode)[0]


def resolve_platform_key(platform_name: str) -> Optional[str]:
    """Map a distiller platform name ("1mg", "Apollo Pharmacy", "Tata 1mg") to its rules key."""
    clean = re.sub(r"[^a-z0-9]", "", (platform_name or "").lower())
    if not clean:
        return None
    platforms = load_delivery_rules()["platforms"]
    if clean in platforms:
        return clean
    for needle, key in PLATFORM_ALIASES:
        if needle in clean:
            return key
    return None


def _slab_fee(slabs: List[dict], order_value: float) -> Tuple[float, Optional[str]]:
    """Fee (and condition, e.g. 'prepaid only') of the highest slab with min_order ≤ order value."""
    applicable = [s for s in slabs if order_value >= float(s.get("min_order", 0))]
    slab = max(applicable, key=lambda s: float(s.get("min_order", 0))) if applicable else slabs[0]
    return float(slab["fee"]), slab.get("condition")


def _inr(amount: float) -> str:
    return f"₹{amount:,.0f}" if float(amount).is_integer() else f"₹{amount:,.2f}"


def calculate_delivery_cost(
    platform_name: str,
    item_price: float,
    pincode,
    quantity: int = 1,
) -> dict:
    """
    Delivery quote for buying `quantity` units of a listing at `item_price` on a platform,
    delivered to `pincode`. Free-delivery thresholds are checked against the order value
    (item_price × quantity).

    Returns:
        pincode, zone, zone_assumed, platform_key, order_value, quantity,
        delivery_status        : free | charged | pickup_only | unserviceable | unknown
        delivery_fee           : float, or None when unknown / unserviceable
        platform_fee           : float
        total_landed_cost      : order_value + delivery_fee + platform_fee, or None when not computable
        is_free_delivery       : bool
        serviceable            : bool — home delivery to this PIN is available
        free_delivery_threshold: float or None
        amount_to_free_delivery: extra order value needed for free delivery, or None
        fee_is_estimate        : True for weight-based and unpublished (estimated) fees
        estimated_days         : str
        delivery_label         : one-line text for the UI, always present
    """
    pin = normalize_pincode(pincode)
    zone, zone_assumed = lookup_zone(pin)
    quantity = max(1, int(quantity))
    order_value = round(float(item_price) * quantity, 2)

    quote = {
        "pincode": pin,
        "zone": zone,
        "zone_assumed": zone_assumed,
        "platform_key": None,
        "quantity": quantity,
        "order_value": order_value,
        "delivery_status": "unknown",
        "delivery_fee": None,
        "platform_fee": 0.0,
        "total_landed_cost": None,
        "is_free_delivery": False,
        "serviceable": False,
        "free_delivery_threshold": None,
        "amount_to_free_delivery": None,
        "fee_is_estimate": False,
        "estimated_days": "",
        "delivery_label": "",
    }

    key = resolve_platform_key(platform_name)
    platform = load_delivery_rules()["platforms"].get(key) if key else None
    if not platform:
        quote["delivery_label"] = f"Delivery charges not available for {platform_name or 'this store'}"
        return quote

    zone_cfg = platform.get("zones", {}).get(zone)
    if not zone_cfg:
        quote.update({"platform_key": key,
                      "delivery_label": f"No delivery data for {platform.get('display_name', key)} in this area"})
        return quote
    days = zone_cfg.get("estimated_days") or ""
    platform_fee = float(platform.get("platform_fee") or 0)
    threshold = zone_cfg.get("free_delivery_threshold")
    threshold = float(threshold) if threshold is not None else None
    quote.update({
        "platform_key": key,
        "platform_fee": platform_fee,
        "estimated_days": days,
        "fee_is_estimate": platform.get("fee_type") in ESTIMATED_FEE_TYPES,
    })

    days_l = days.lower()
    if not platform.get("serviceable", True) or zone == "unserviceable" or (
        "non-serviceable" in days_l and "pickup" not in days_l
    ):
        quote.update({"delivery_status": "unserviceable",
                      "delivery_label": f"Does not deliver to PIN {pin}"})
        return quote

    if "pickup" in days_l and "non-serviceable" in days_l:
        quote.update({
            "delivery_status": "pickup_only",
            "delivery_fee": 0.0,
            "total_landed_cost": round(order_value + platform_fee, 2),
            "delivery_label": f"No home delivery to PIN {pin} — store pickup only",
        })
        return quote

    condition = None
    if zone_cfg.get("order_value_slabs"):
        fee, condition = _slab_fee(zone_cfg["order_value_slabs"], order_value)
        always_free = _slab_fee(zone_cfg["order_value_slabs"], 0)[0] == 0
    elif zone_cfg.get("delivery_fee") is not None:
        fee = float(zone_cfg["delivery_fee"])
        always_free = fee == 0
    else:
        quote.update({"serviceable": True,
                      "delivery_label": f"Delivers to PIN {pin}, but delivery fee is not published"})
        return quote

    if threshold is not None and order_value >= threshold:
        fee = 0.0

    quote.update({
        "serviceable": True,
        "delivery_fee": fee,
        "is_free_delivery": fee == 0,
        "delivery_status": "free" if fee == 0 else "charged",
        "free_delivery_threshold": threshold,
        "total_landed_cost": round(order_value + fee + platform_fee, 2),
    })

    if fee == 0:
        if always_free or not threshold:
            label = "FREE delivery on every order"
        else:
            label = f"FREE delivery (order ≥ {_inr(threshold)})"
    else:
        approx = "~" if quote["fee_is_estimate"] else ""
        label = f"{approx}{_inr(fee)} delivery"
        if condition:
            label += f" ({condition})"
        if quote["fee_is_estimate"]:
            label += " (weight-based estimate)" if platform.get("fee_type") in WEIGHT_FEE_TYPES else " (estimated fee)"
        if threshold is not None and threshold > order_value:
            gap = round(threshold - order_value, 2)
            quote["amount_to_free_delivery"] = gap
            label += f" · add {_inr(gap)} more for FREE delivery"
        else:
            label += " · no free-delivery offer"
    if platform_fee:
        label += f" · +{_inr(platform_fee)} platform fee"
    quote["delivery_label"] = label
    return quote
