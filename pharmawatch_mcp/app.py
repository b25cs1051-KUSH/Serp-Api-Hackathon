"""The MCPServer instance: name, instructions for the model, start-up."""

import threading
from contextlib import asynccontextmanager

import api.main as api
from mcp.server.mcpserver import MCPServer

INSTRUCTIONS = (
    "PharmaWatch finds where an Indian medicine is cheapest once delivery to the buyer's PIN code is included, "
    "and which brands with the same salt, strength and form cost less. Prices are live Google Shopping data via "
    "SerpApi, cached in Redis for 24 h.\n"
    "Workflow: search_medicine for one medicine, plan_prescription for several (it optimises the whole basket "
    "across pharmacies, delivery fees included). Show the user the delivered price ('you pay'), not the shelf "
    "price. Every listing has a listing_id: when the user wants to buy one, call get_buy_link(listing_id) for "
    "that pharmacy's own product page.\n"
    "If a medicine name has no strength (e.g. 'paracetamol'), the tools return the options instead of searching "
    "(0 credits): ask the user which one is on the prescription.\n"
    "Credits: a new medicine costs about 4 SerpApi credits (main search plus up to 3 same-salt searches); repeat "
    "or similar searches are free from cache. get_buy_link costs 1 credit the first time per listing, then 0 for "
    "24 h. cache_lab predicts the main lookup for free. Keep resolve_links false and use get_buy_link for the "
    "listing the user actually picks.\n"
    "Always tell the user that swaps have the same salt, strength and form, and that they should check with a "
    "doctor or pharmacist before switching. This is price information, not medical advice."
)


@asynccontextmanager
async def lifespan(server: MCPServer):
    # Load the embedding model off the request path, once per process. Over HTTP the API has
    # usually done it already; stateless HTTP enters this lifespan on every request.
    if api._state["warm"] == "pending":
        threading.Thread(target=api._warm, daemon=True, name="warm-up").start()
    yield


mcp = MCPServer(
    name="pharmawatch",
    title="PharmaWatch",
    version="0.3.0",
    instructions=INSTRUCTIONS,
    lifespan=lifespan,
)
