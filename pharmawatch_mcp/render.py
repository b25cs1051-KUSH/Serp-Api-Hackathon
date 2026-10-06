"""Markdown for each output model: compact, readable text for the model's context window."""

from typing import Optional

from .models import (
    CAUTION,
    BuyLinkOutput,
    Generic,
    LabOutput,
    NeedsStrength,
    PrescriptionOutput,
    RunSummary,
    SearchOutput,
    StatsOutput,
)

MAX_ROWS = 10  # listings shown in Markdown; structuredContent always has every listing

LINK_NOTE = ("Buy: `product page` opens the pharmacy's own page. For an `id`, call get_buy_link with it to get "
             "that pharmacy's product page (1 SerpApi credit the first time, then cached for 24 h).")


# ── Helpers ──────────────────────────────────────────────────────────────────

def inr(value) -> str:
    return "—" if value is None else f"₹{value:,.2f}"


def cell(text) -> str:
    return str(text or "—").replace("|", "\\|").replace("\n", " ")


def buy_cell(x) -> str:
    """A product page as a link; otherwise the store search link and the id for get_buy_link."""
    if x.link_type == "product_page":
        return f"[product page]({x.link})"
    parts = []
    if x.link_type == "store_search":
        parts.append(f"[store search]({x.link})")
    if x.listing_id:
        parts.append(f"id `{x.listing_id}`")
    return " · ".join(parts) or "—"


def pack(g: Generic) -> str:
    if not g.pack_size:
        return "—"
    return f"~{g.pack_size} (est.)" if g.pack_estimated else str(g.pack_size)


def run_line(run: Optional[RunSummary]) -> str:
    if not run:
        return "No run summary."
    return (f"{run.serpapi_lookups} SerpApi lookups · {run.credits_spent} credit{'' if run.credits_spent == 1 else 's'} "
            f"spent · {run.from_cache} served from cache ({run.exact_hits} exact, {run.semantic_hits} semantic) · "
            f"{run.seconds:.1f} s")


def _error_line(error: str, prefix: str) -> list[str]:
    code, _, message = error.partition(": ")
    return [f"> **{prefix} ({code}):** {message}", ""]


def _needs(n: NeedsStrength, tool: str) -> list[str]:
    out = [f"## Which {n.medicine}?", "",
           "It comes in more than one strength or form, so nothing was searched yet (0 credits). "
           f"Ask the user which one is on their prescription, then call {tool} again with it:", ""]
    return out + [f"- {o.label}: `{o.query}`" for o in n.options]


# ── search_medicine ──────────────────────────────────────────────────────────

def _generics_table(s: SearchOutput) -> list[str]:
    rows = s.cheaper_generics or (s.other_generics if not s.reference else [])
    if not rows:
        return ["No cheaper same-salt brand found online right now."]
    with_saving = bool(s.cheaper_generics)
    out = ["", "| Brand | Maker | Pharmacy | You pay | Per tablet | Pack |" + (" Saving |" if with_saving else "") + " Buy |",
           "|---|---|---|---|---|---|" + ("---|" if with_saving else "") + "---|"]
    for g in rows:
        saving = ""
        if with_saving:
            approx = "≈" if g.saving_estimated else ""
            basis = "/tablet" if g.saving_basis == "per_tablet" else ""
            saving = f" {approx}{g.saving_pct}% ({inr(g.saving_inr)}{basis}) |" if g.saving_pct is not None else " — |"
        out.append(f"| {cell(g.brand)} | {cell(g.manufacturer)} | {cell(g.pharmacy)} | {inr(g.you_pay_inr)} | "
                   f"{inr(g.per_tablet_inr)} | {pack(g)} |{saving} {buy_cell(g)} |")
    out.append("\nPer tablet includes delivery. ~ = pack size estimated, ≈ = saving depends on it. " + CAUTION)
    return out


def search(s: SearchOutput) -> str:
    if s.needs_strength:
        return "\n".join(_needs(s.needs_strength, "search_medicine"))
    out = [f"## {s.medicine}: delivered prices to PIN {s.pincode}", ""]
    if s.spelling_corrected:
        out += [f"_Read \"{s.query}\" as **{s.medicine}** (spelling corrected). Confirm with the user if unsure._", ""]
    if s.error:
        out += _error_line(s.error, "Search incomplete")
    if s.listings:
        if s.cheapest:
            out += [f"Cheapest delivered: **{inr(s.cheapest.you_pay_inr)}** at {s.cheapest.pharmacy} "
                    f"({s.cheapest.delivery or s.cheapest.delivery_status}).", ""]
        out += ["| # | Pharmacy | Product | Shelf price | Delivery | You pay | Arrives | Buy |",
                "|---|---|---|---|---|---|---|---|"]
        for i, x in enumerate(s.listings[:MAX_ROWS], 1):
            out.append(f"| {x.rank or i} | {cell(x.pharmacy)} | {cell(x.product)} | {inr(x.shelf_price_inr)} | "
                       f"{cell(x.delivery)} | {inr(x.you_pay_inr)} | {cell(x.arrives)} | {buy_cell(x)} |")
        if len(s.listings) > MAX_ROWS:
            out.append(f"\n{len(s.listings) - MAX_ROWS} more listings in structuredContent (or response_format='json').")
    else:
        out.append("No listings found for this medicine.")

    out.append("")
    comp = s.composition
    if not comp:
        out.append("### Same-salt brands\nNot in the 246,000-medicine index, so no substitutes were compared.")
    else:
        out.append(f"### Same-salt brands: {comp.name or comp.active_ingredient}")
        if s.reference:
            unit = f", {inr(s.reference.per_tablet_inr)}/tablet delivered" if s.reference.per_tablet_inr is not None else ""
            out.append(f"Reference: {cell(s.reference.product)} at {s.reference.pharmacy}, "
                       f"{inr(s.reference.you_pay_inr)}{unit}.")
        out += _generics_table(s)
        if s.not_sold_here:
            out.append(f"Not deliverable here right now: {', '.join(s.not_sold_here)}.")
    out += ["", LINK_NOTE, "", "### Run", run_line(s.run)]
    return "\n".join(out)


# ── plan_prescription ────────────────────────────────────────────────────────

def prescription(p: PrescriptionOutput) -> str:
    out = [f"## Prescription: cheapest way to buy it, delivered to PIN {p.pincode}", ""]
    if p.error:
        out += _error_line(p.error, "Incomplete")
    for n in p.needs_strength:
        opts = ", ".join(f"`{o.query}`" for o in n.options[:6])
        out += [f"**Which {n.medicine}?** Left out until the user picks one (0 credits): {opts}", ""]
    if not p.plans:
        return "\n".join(out + ["No basket could be built.", "", "### Run", run_line(p.run)])

    best = p.plans[0]
    out.append(f"**{best.title}: {inr(best.total_inr)}** ({inr(best.medicines_inr)} medicines + "
               f"{inr(best.delivery_inr)} delivery), {len(best.orders)} order{'s' if len(best.orders) > 1 else ''}: "
               f"{' + '.join(o.pharmacy for o in best.orders)}.")
    if p.saving_vs_prescribed_inr:
        out.append(f"That is {inr(p.saving_vs_prescribed_inr)} less than the prescribed brands "
                   f"(compared on {len(p.saving_covers)} medicine{'s' if len(p.saving_covers) != 1 else ''} sold online).")
    out += ["", "| Order at | Medicine | Buy | Packs | Cost | Per unit | Link |", "|---|---|---|---|---|---|---|"]
    for o in best.orders:
        for it in o.items:
            buy = it.buy + (" (same-salt swap)" if it.is_swap else "")
            packs = f"{it.packs} × {'~' if it.pack_estimated else ''}{it.pack_size or '?'}"
            out.append(f"| {cell(o.pharmacy)} | {cell(it.medicine)} | {cell(buy)} | {packs} | {inr(it.cost_inr)} | "
                       f"{inr(it.per_unit_inr)} | {buy_cell(it)} |")
    out.append("")
    out += [f"- {o.pharmacy}: {inr(o.subtotal_inr)} + {inr(o.delivery_fee_inr)} delivery = {inr(o.total_inr)}"
            for o in best.orders]
    if len(p.plans) > 1:
        out += ["", "Other ways to buy it:"]
        for pl in p.plans[1:]:
            diff = pl.total_inr - best.total_inr
            out.append(f"- {pl.title}: {inr(pl.total_inr)} ({' + '.join(o.pharmacy for o in pl.orders)})"
                       + (f", {inr(diff)} more" if diff > 0.005 else ""))
    if p.not_sold_here:
        out.append(f"\nNot sold online for this PIN: {', '.join(p.not_sold_here)}.")
    out += ["", "Cost and per-unit prices are before delivery; delivery is added per order. " + CAUTION,
            "", LINK_NOTE, "", "### Run", run_line(p.run)
            + (f" · {p.combinations_priced:,} basket combinations priced" if p.combinations_priced else "")]
    return "\n".join(out)


# ── get_buy_link, cache_lab, cache_stats ─────────────────────────────────────

def buy_link(b: BuyLinkOutput) -> str:
    what = "Product page" if b.is_product_page else "Product page not found; the pharmacy's search page instead"
    return (f"**{what}** for {b.product or 'this listing'} at {b.pharmacy}: {b.url}\n\n"
            f"{b.credits_spent} credit{'s' if b.credits_spent != 1 else ''} spent · {b.seconds:.1f} s")


def lab(lab_out: LabOutput) -> str:
    verdict = {"exact_hit": "EXACT HIT (0 credits)", "semantic_hit": "SEMANTIC HIT (0 credits)",
               "api_call": "SERPAPI CALL (1 credit)"}[lab_out.decision]
    t = lab_out.timings_ms
    out = [f"## Cache Lab: \"{lab_out.input}\"", "",
           f"Decision: **{verdict}**. {lab_out.reason}.", "",
           f"Normalized query `{lab_out.normalized_query}` · threshold {lab_out.threshold} · compared against "
           f"{lab_out.compared_against} cached queries · exact lookup {t.get('exact_lookup')} ms, embed {t.get('embed')} ms, "
           f"scan {t.get('scan')} ms", ""]
    if not lab_out.nearest:
        return "\n".join(out + ["No cached price searches to compare against."])
    out += ["| Cached query | Similarity | ≥ threshold | Same params | Dosage guard |", "|---|---|---|---|---|"]
    out += [f"| {cell(c.cached_query)} | {c.similarity:.3f} | {'yes' if c.above_threshold else 'no'} | "
            f"{'yes' if c.same_params else 'NO'} | {'BLOCKS' if c.dosage_guard_blocks else '—'} |" for c in lab_out.nearest]
    return "\n".join(out)


def stats(s: StatsOutput) -> str:
    sess = s.session
    counts = ", ".join(f"{v} {k}" for k, v in s.cached_entries.items()) or "nothing"
    return "\n".join([
        "## PharmaWatch cache",
        "",
        f"- Redis: {'up' if s.redis_ok else 'DOWN (passthrough: every lookup costs a credit)'}",
        f"- Embedding model: {s.embedding_model} · similarity threshold {s.similarity_threshold}",
        f"- Keys configured: SerpApi {'yes' if s.serpapi_key_configured else 'no'}, "
        f"Gemini {'yes' if s.gemini_key_configured else 'no'}",
        f"- Cached: {counts} ({s.cached_bytes / 1024:.1f} KB)",
        f"- This session: {sess['searches']} searches, {sess['serpapi_calls']} lookups, {sess['credits_spent']} credits "
        f"spent, {sess['credits_saved']} saved ({sess['exact_hits']} exact, {sess['semantic_hits']} semantic, "
        f"hit rate {sess['hit_rate_pct']}%)",
    ])
