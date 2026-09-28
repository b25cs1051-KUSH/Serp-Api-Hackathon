"use client";

import { BadgeCheck, ExternalLink, FlaskConical, Pill as PillIcon, ShieldCheck, Store } from "lucide-react";
import { inr, type Alternative, type AltResult } from "@/lib/api";

export default function Alternatives({ result, running }: { result: AltResult | null | undefined; running: boolean }) {
  if (result === undefined) {
    return running ? (
      <div className="card p-5">
        <div className="mb-3 h-5 w-56 rounded shimmer" />
        <div className="h-24 rounded-lg shimmer" />
      </div>
    ) : null;
  }
  if (result === null) {
    return (
      <div className="card p-5 text-sm text-muted">
        <div className="mb-1 flex items-center gap-2 font-semibold text-ink">
          <ShieldCheck className="h-4 w-4 text-faint" /> No substitutes suggested
        </div>
        We couldn&apos;t identify this medicine&apos;s salt in our medicine index, so no substitute is suggested. We never guess on medicines.
      </div>
    );
  }

  const ref = result.reference;
  const c = result.composition;
  const shown = result.cheaper_alternatives.length + result.other_alternatives.length;
  const how =
    result.matched_by === "gemini"
      ? "Spelling fixed by Gemini, checked against the medicine index"
      : result.matched_by === "fuzzy"
        ? "Spelling corrected from the medicine index"
        : "Identified in a 246,000-medicine index";

  return (
    <div className="card p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-llm" />
            <h3 className="text-lg font-semibold">{result.matched_as === "salt" ? `Brands of ${c.name}` : "Same medicine, other brands"}</h3>
          </div>
          <p className="mt-1 text-sm text-muted">
            <span className="text-ink">{c.name}</span>
            {c.drug_class && <> · {c.drug_class}</>}
            {c.brand_count != null && (
              <> · {shown} of {c.brand_count} brand{c.brand_count === 1 ? "" : "s"} found online here</>
            )}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-panel-2 px-3 py-2 text-[11px] text-muted">
          <div className="flex items-center gap-1 text-ink">
            <BadgeCheck className="h-3.5 w-3.5 text-hit" />
            {how}
          </div>
          <div className="mt-0.5 max-w-xs">{result.match_reason}</div>
        </div>
      </div>

      {ref && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-bg/50 px-3 py-2 text-xs">
          <span className="text-muted">
            You searched <span className="font-medium text-ink">{result.matched_brand}</span>: best delivered at {ref.platform}
          </span>
          <span className="tnum font-mono text-ink">
            {inr(ref.total_landed_cost)}
            {ref.unit_landed_cost != null && <span className="text-faint"> · {inr(ref.unit_landed_cost)}/tab</span>}
          </span>
        </div>
      )}

      <div className="space-y-2">
        {result.cheaper_alternatives.map((a) => (
          <AltRow key={`c-${a.brand}`} alt={a} cheaper />
        ))}
        {result.other_alternatives.map((a) => (
          <AltRow key={`o-${a.brand}`} alt={a} />
        ))}
      </div>

      {result.not_found.length > 0 && (
        <p className="mt-3 text-xs text-faint">Searched, but not sold online for this PIN right now: {result.not_found.join(", ")}</p>
      )}
      <p className="mt-3 flex items-center gap-1 text-[11px] text-faint">
        <PillIcon className="h-3 w-3" /> Only brands with the same salt, strength, form and release type are shown (Indian Medicine Dataset). Check with your doctor before switching.
      </p>
    </div>
  );
}

function AltRow({ alt, cheaper = false }: { alt: Alternative; cheaper?: boolean }) {
  const href = alt.direct_link || alt.search_link || alt.google_link;
  return (
    <div className={`rise flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2.5 ${cheaper ? "border-hit/30 bg-hit/[0.05]" : "border-line bg-panel-2"}`}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{alt.brand}</span>
          <span className="text-xs text-muted">at {alt.platform}</span>
          {cheaper && alt.savings_pct != null && (
            <span
              className="rounded bg-hit/15 px-1.5 py-0.5 text-[10px] font-bold text-hit"
              title={alt.estimated ? "Based on an estimated pack size" : undefined}
            >
              SAVE {alt.estimated ? "≈" : ""}{alt.savings_pct}%
            </span>
          )}
          {alt.widely_stocked && (
            <span className="inline-flex items-center gap-1 rounded bg-sem/10 px-1.5 py-0.5 text-[10px] font-semibold text-sem" title="Sold by 3 or more pharmacies for this PIN">
              <Store className="h-3 w-3" /> Widely stocked
            </span>
          )}
        </div>
        <div className="mt-0.5 line-clamp-1 text-xs text-faint" title={alt.medicine_name}>
          {alt.manufacturer ? `${alt.manufacturer} · ` : ""}
          {alt.medicine_name}
        </div>
      </div>
      <div className="text-right">
        <div className="tnum font-mono text-sm font-semibold">{inr(alt.total_landed_cost)}</div>
        <div className="tnum text-[11px] text-muted">
          {alt.unit_landed_cost != null ? `${inr(alt.unit_landed_cost)}/tab` : "total"}
          {alt.pack_size ? (alt.pack_estimated ? ` · ~${alt.pack_size} tabs (estimated)` : ` · ${alt.pack_size} tabs`) : ""}
          {cheaper && alt.savings != null && <span className="text-hit"> · −{inr(alt.savings)}{alt.price_basis === "per_tablet" ? "/tab" : ""}</span>}
        </div>
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium text-muted ring-1 ring-line hover:text-ink"
      >
        {alt.direct_link ? "Visit site" : "Search"} <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
