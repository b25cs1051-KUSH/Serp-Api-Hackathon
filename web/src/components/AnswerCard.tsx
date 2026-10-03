"use client";

import { AlertTriangle, ArrowDown, ExternalLink, Stethoscope } from "lucide-react";
import { buyLink, inr, type AltResult, type Listing } from "@/lib/api";

/** Shop view: the answer to "where do I buy it, and is there a cheaper brand?", above the full list. */
export default function AnswerCard({
  query,
  listings,
  alternatives,
  running,
}: {
  query: string;
  listings: Listing[] | null;
  alternatives: AltResult | null | undefined;
  running: boolean;
}) {
  if (listings === null) {
    return (
      <div className="card grid gap-4 p-6 md:grid-cols-2">
        <div className="space-y-3">
          <div className="h-3 w-40 rounded shimmer" />
          <div className="h-8 w-64 rounded shimmer" />
          <div className="h-4 w-56 rounded shimmer" />
        </div>
        <div className="h-24 rounded-lg shimmer" />
      </div>
    );
  }

  if (listings.length === 0) {
    return (
      <div className="card p-6">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">No exact match online</div>
        <p className="mt-2 text-lg font-semibold">We couldn&apos;t find {query} for sale online right now.</p>
        <p className="mt-1 text-sm text-muted">
          Similar-looking products were left out on purpose, so you never buy the wrong medicine. Check the spelling, or try the salt name.
        </p>
      </div>
    );
  }

  const best = listings.find((l) => l.is_cheapest) ?? listings[0];
  const href = buyLink(best);
  const lowestShelf = listings.reduce((a, b) => (b.price_inr < a.price_inr ? b : a));
  const shelfFees = lowestShelf.total_landed_cost != null ? lowestShelf.total_landed_cost - lowestShelf.price_inr : null;
  const showShelfWarning =
    lowestShelf !== best &&
    best.total_landed_cost != null &&
    lowestShelf.total_landed_cost != null &&
    lowestShelf.total_landed_cost > best.total_landed_cost &&
    shelfFees != null &&
    shelfFees > 0;

  return (
    <div className="space-y-3">
      <div className="rise grid overflow-hidden rounded-2xl border border-hit/40 bg-hit/[0.06] md:grid-cols-2">
        <div className="p-6">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">Best delivered price</div>
          <div className="mt-2 text-3xl font-semibold tracking-tight">
            <span className="tnum">{inr(best.total_landed_cost)}</span> <span className="text-muted font-normal">at</span> {best.platform}
          </div>
          <p className="mt-2 text-sm text-muted">
            {best.delivery_status === "free" ? "Free delivery" : best.delivery_label}
            {best.estimated_days && <> · arrives in {best.estimated_days}</>}
          </p>
          <p className="mt-0.5 line-clamp-1 text-xs text-faint" title={best.medicine_name}>
            {best.medicine_name}
            {best.manufacturer && <> · by {best.manufacturer}</>}
          </p>
          {href && (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-hit px-4 py-2.5 text-sm font-semibold text-bg transition hover:brightness-110"
            >
              Buy at {best.platform} <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
        <div className="border-t border-hit/20 p-6 md:border-l md:border-t-0">
          <CheaperBrand alternatives={alternatives} running={running} />
        </div>
      </div>

      {showShelfWarning && (
        <div className="rise flex items-start gap-2 rounded-xl border border-miss/30 bg-miss/[0.07] px-4 py-3 text-sm text-miss">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            The lowest shelf price is <span className="tnum font-semibold">{inr(lowestShelf.price_inr)}</span> at {lowestShelf.platform}, but you pay{" "}
            <span className="tnum font-semibold">{inr(lowestShelf.total_landed_cost)}</span> after{" "}
            <span className="tnum">{inr(shelfFees)}</span> in delivery charges.
          </span>
        </div>
      )}
    </div>
  );
}

function CheaperBrand({ alternatives, running }: { alternatives: AltResult | null | undefined; running: boolean }) {
  if (alternatives === undefined) {
    return running ? (
      <div className="space-y-3">
        <div className="h-3 w-44 rounded shimmer" />
        <div className="h-6 w-60 rounded shimmer" />
        <div className="h-4 w-48 rounded shimmer" />
      </div>
    ) : null;
  }

  if (alternatives && alternatives.matched_as === "salt") {
    // A salt search has no "your brand" to beat: show the cheapest brand per tablet among those compared.
    const perTab = [...alternatives.other_alternatives, ...alternatives.cheaper_alternatives]
      .filter((a) => a.unit_landed_cost != null)
      .sort((a, b) => (a.unit_landed_cost ?? 0) - (b.unit_landed_cost ?? 0))[0];
    const compared = alternatives.other_alternatives.length + alternatives.cheaper_alternatives.length;
    return (
      <>
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">Cheapest per tablet</div>
        {perTab ? (
          <>
            <p className="mt-2 text-xl font-semibold">
              {perTab.brand} at <span className="tnum">{perTab.pack_estimated ? "~" : ""}{inr(perTab.unit_landed_cost)}</span> a tablet
            </p>
            <p className="mt-1 text-sm text-muted">
              {perTab.manufacturer && <>by {perTab.manufacturer} · </>}
              {compared} brand{compared === 1 ? "" : "s"} of {alternatives.composition.name} compared
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">Pack sizes are missing, so brands are compared on the total price.</p>
        )}
        <p className="mt-2 flex items-center gap-1.5 text-xs text-faint">
          <Stethoscope className="h-3.5 w-3.5" /> Same salt and strength. Ask your doctor or pharmacist which brand suits you.
        </p>
        <a href="#alternatives" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-hit hover:underline">
          See every brand <ArrowDown className="h-3.5 w-3.5" />
        </a>
      </>
    );
  }

  const top = alternatives?.cheaper_alternatives[0];
  if (!alternatives || !top) {
    return (
      <>
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Cheaper brand</div>
        <p className="mt-2 text-sm text-muted">
          {alternatives
            ? "No brand with the same salt is cheaper online right now."
            : "We couldn't identify this medicine's salt, so we don't suggest substitutes."}
        </p>
      </>
    );
  }

  const ref = alternatives.reference;
  const perTablet = top.price_basis === "per_tablet" && top.unit_landed_cost != null && ref?.unit_landed_cost != null;
  return (
    <>
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">Same salt, lower price</div>
      <p className="mt-2 text-xl font-semibold">
        {top.brand} costs {top.estimated ? "about " : ""}
        {Math.round(top.savings_pct ?? 0)}% less{perTablet ? " per tablet" : ""}
      </p>
      <p className="mt-1 text-sm text-muted">
        {perTablet && (
          <span className="tnum">
            {inr(top.unit_landed_cost)} vs {inr(ref?.unit_landed_cost)} per tablet ·{" "}
          </span>
        )}
        {alternatives.composition.active_ingredient}
        {top.manufacturer && <> · by {top.manufacturer}</>}
      </p>
      <p className="mt-2 flex items-center gap-1.5 text-xs text-faint">
        <Stethoscope className="h-3.5 w-3.5" /> Ask your doctor or pharmacist before switching brands.
      </p>
      <a href="#alternatives" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-hit hover:underline">
        See cheaper brands <ArrowDown className="h-3.5 w-3.5" />
      </a>
    </>
  );
}
