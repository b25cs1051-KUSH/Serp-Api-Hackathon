"""Typed tool inputs and outputs. Each output model is published as its tool's outputSchema."""

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field

LinkType = Literal["product_page", "store_search", "google_shopping"]
CAUTION = "Same salt, strength and form. Ask a doctor or pharmacist before switching brands."


# ── Inputs ───────────────────────────────────────────────────────────────────

ResponseFormat = Annotated[
    Literal["markdown", "json"],
    Field(description="Text form of the result: 'markdown' (default, compact and readable) or 'json'. "
                      "Typed structuredContent is returned either way."),
]


class PrescriptionItem(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=120,
                               description="Medicine as written on the prescription: brand or salt with strength, "
                                           "e.g. 'Dolo 650', 'Atorvastatin 10mg'.")]
    tablets: Annotated[Optional[int], Field(default=None, ge=1, le=500,
                                            description="Tablets (or items, for syrups and creams) needed. "
                                                        "Omit to buy one pack.")] = None


# ── Shared pieces ────────────────────────────────────────────────────────────

class RunSummary(BaseModel):
    serpapi_lookups: int = Field(description="SerpApi requests made, cached or not")
    credits_spent: int = Field(description="Lookups that called SerpApi (cache misses)")
    from_cache: int
    exact_hits: int
    semantic_hits: int
    seconds: float


class StrengthOption(BaseModel):
    label: str
    query: str = Field(description="Call the tool again with this as the medicine name")


class NeedsStrength(BaseModel):
    medicine: str
    options: list[StrengthOption]


# ── search_medicine ──────────────────────────────────────────────────────────

class Listing(BaseModel):
    rank: Optional[int] = None
    pharmacy: str
    product: str = Field(description="Title as the pharmacy lists it")
    shelf_price_inr: Optional[float] = None
    delivery_fee_inr: Optional[float] = Field(None, description="Null when the pharmacy doesn't publish it")
    platform_fee_inr: Optional[float] = None
    you_pay_inr: Optional[float] = Field(None, description="Shelf price + delivery + platform fee to this PIN")
    delivery: Optional[str] = Field(None, description="One-line delivery explanation")
    delivery_status: Optional[str] = None
    arrives: Optional[str] = None
    is_cheapest: bool = False
    listing_id: Optional[str] = Field(None, description="Pass to get_buy_link for the product page")
    link: Optional[str] = None
    link_type: Optional[LinkType] = None


class Generic(BaseModel):
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    pharmacy: Optional[str] = None
    product: Optional[str] = None
    you_pay_inr: Optional[float] = None
    per_tablet_inr: Optional[float] = Field(None, description="Delivered cost per tablet (delivery included)")
    pack_size: Optional[int] = None
    pack_estimated: bool = False
    saving_inr: Optional[float] = None
    saving_pct: Optional[float] = None
    saving_basis: Optional[str] = Field(None, description="'per_tablet' or 'total'")
    saving_estimated: bool = Field(False, description="True when the saving depends on an estimated pack size")
    widely_stocked: Optional[bool] = None
    listing_id: Optional[str] = None
    link: Optional[str] = None
    link_type: Optional[LinkType] = None


class Composition(BaseModel):
    name: Optional[str] = None
    active_ingredient: Optional[str] = None
    brands_with_same_composition: Optional[int] = None


class SearchOutput(BaseModel):
    query: str = Field(description="What the user typed")
    medicine: str = Field(description="The medicine actually searched (spelling corrected if needed)")
    spelling_corrected: bool = False
    pincode: str
    needs_strength: Optional[NeedsStrength] = Field(None, description="Set when nothing was searched yet")
    composition: Optional[Composition] = None
    cheapest: Optional[Listing] = Field(None, description="Cheapest listing that can be delivered")
    listings: list[Listing] = Field(default_factory=list, description="Ranked by delivered price")
    reference: Optional[Generic] = Field(None, description="The searched brand's best per-tablet offer")
    cheaper_generics: list[Generic] = Field(default_factory=list)
    other_generics: list[Generic] = Field(default_factory=list)
    not_sold_here: list[str] = Field(default_factory=list, description="Same-salt brands searched but not deliverable")
    caution: str = CAUTION
    run: Optional[RunSummary] = None
    error: Optional[str] = Field(None, description="Set when the search finished only partly")


# ── plan_prescription ────────────────────────────────────────────────────────

class BasketItem(BaseModel):
    medicine: str = Field(description="The prescription line this item covers")
    buy: str = Field(description="Brand to buy")
    is_swap: bool = Field(description="True when it replaces the prescribed brand with the same salt")
    product: Optional[str] = None
    manufacturer: Optional[str] = None
    packs: int
    pack_size: Optional[int] = None
    pack_estimated: bool = False
    unit: str = Field("tablet", description="'tablet', or 'item' for syrups, creams and similar")
    cost_inr: float = Field(description="Packs × shelf price, before delivery")
    per_unit_inr: Optional[float] = Field(None, description="Per tablet (or item), before delivery")
    listing_id: Optional[str] = None
    link: Optional[str] = None
    link_type: Optional[LinkType] = None


class Order(BaseModel):
    pharmacy: str
    items: list[BasketItem]
    subtotal_inr: float
    delivery_fee_inr: float
    total_inr: float
    free_delivery: bool
    delivery: Optional[str] = None


class Plan(BaseModel):
    plan: Literal["cheapest_with_swaps", "one_pharmacy", "as_prescribed"]
    title: str
    total_inr: float
    medicines_inr: float
    delivery_inr: float
    orders: list[Order]


class MedicineView(BaseModel):
    medicine: str
    units_needed: Optional[int] = None
    units_how: Optional[str] = Field(None, description="'typed' or 'one pack'")
    cheapest_prescribed: Optional[BasketItem] = None
    cheapest_any: Optional[BasketItem] = None


class PrescriptionOutput(BaseModel):
    pincode: str
    plans: list[Plan] = Field(default_factory=list,
                              description="Cheapest with swaps, best single pharmacy, exactly as prescribed")
    saving_vs_prescribed_inr: Optional[float] = None
    saving_covers: list[str] = Field(default_factory=list, description="Medicines the saving is computed on")
    per_medicine: list[MedicineView] = Field(default_factory=list)
    needs_strength: list[NeedsStrength] = Field(default_factory=list, description="Lines left out until chosen")
    not_sold_here: list[str] = Field(default_factory=list)
    combinations_priced: Optional[int] = None
    caution: str = CAUTION
    run: Optional[RunSummary] = None
    error: Optional[str] = None


# ── get_buy_link, cache_lab, cache_stats ─────────────────────────────────────

class BuyLinkOutput(BaseModel):
    listing_id: str
    pharmacy: Optional[str] = None
    product: Optional[str] = None
    url: str
    is_product_page: bool = Field(description="False when only the pharmacy's search page could be found")
    credits_spent: int
    seconds: float


class NearQuery(BaseModel):
    cached_query: str
    similarity: float
    above_threshold: bool
    same_params: bool
    dosage_guard_blocks: bool


class LabOutput(BaseModel):
    input: str
    decision: Literal["exact_hit", "semantic_hit", "api_call"]
    reason: str
    credits_if_searched: int
    normalized_query: str
    threshold: float
    compared_against: int
    timings_ms: dict[str, float]
    nearest: list[NearQuery]


class StatsOutput(BaseModel):
    redis_ok: bool
    embedding_model: str
    similarity_threshold: float
    serpapi_key_configured: bool
    gemini_key_configured: bool
    cached_entries: dict[str, int]
    cached_bytes: int
    session: dict[str, Any] = Field(description="Counters for this server process since it started")
