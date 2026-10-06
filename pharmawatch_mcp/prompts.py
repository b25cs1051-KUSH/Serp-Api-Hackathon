"""Prompts: ready-made requests that MCP clients can show as one-click actions."""

from .app import mcp


@mcp.prompt(title="Compare a medicine's prices")
def compare_medicine(medicine: str, pincode: str) -> str:
    """Where is this medicine cheapest delivered to my PIN, and is there a cheaper same-salt brand?"""
    return (f"Find where {medicine} is cheapest delivered to PIN {pincode} in India. Use the PharmaWatch "
            "search_medicine tool. If it asks which strength, ask me before searching again. Show the 5 cheapest "
            "offers by the price I actually pay (delivery included) with pharmacy, delivery and arrival time, then "
            "any cheaper brand with the same salt and strength and how much it saves per tablet. Remind me to check "
            "with my doctor or pharmacist before switching brands. When I pick an offer, use get_buy_link to give me "
            "the pharmacy's product page.")


@mcp.prompt(title="Plan my prescription")
def plan_my_prescription(prescription: str, pincode: str) -> str:
    """Cheapest way to buy a whole prescription, delivery included."""
    return (f"Here is my prescription, one medicine per line (with the number of tablets if given):\n{prescription}\n\n"
            f"Find the cheapest way to buy all of it delivered to PIN {pincode}. Use the PharmaWatch "
            "plan_prescription tool. Show the cheapest plan as orders per pharmacy with each item, packs and cost, the "
            "delivery per order and the total, then the one-pharmacy and exactly-as-prescribed totals for comparison. "
            "Mark same-salt swaps and remind me to check them with my doctor or pharmacist. If a medicine needs a "
            "strength, ask me. When I'm ready to buy, use get_buy_link for each item I choose.")
