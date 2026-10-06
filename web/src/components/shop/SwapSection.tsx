"use client";

import { BadgeCheck, ShieldCheck, Store } from "lucide-react";
import PharmacyLogo from "@/components/PharmacyLogo";
import { inr, type Alternative, type AltResult } from "@/lib/api";
import { BuyLink } from "./ProductCard";

const CAUTION = "Same salt, strength and form. Ask your doctor or pharmacist before switching brands.";

const perUnit = (a: Alternative) =>
  a.unit_landed_cost != null ? `${a.pack_estimated ? "~" : ""}${inr(a.unit_landed_cost)} per tablet` : `${inr(a.total_landed_cost)} delivered`;

/** "Same salt, same strength: X at ₹y per tablet. Save N%", with its Buy link and the caution. */
function SwapStrip({ a }: { a: Alternative }) {
  return (
    <li className="rise rounded-xl border border-hit/40 bg-hit/[0.07] p-4">
      <div className="flex items-start gap-3">
        <PharmacyLogo platform={a.platform} src={a.platform_logo} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="text-sm">
            <span className="text-muted">Same salt, same strength: </span>
            <span className="font-semibold">{a.brand}</span> at <span className="tnum font-mono">{perUnit(a)}</span>.
            {a.savings_pct != null && (
              <span className="ml-1 font-semibold text-hit">
                Save {a.estimated ? "≈" : ""}
                {a.savings_pct}%
              </span>
            )}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
            <span>
              {a.platform} · <span className="tnum font-mono">{inr(a.total_landed_cost)}</span> delivered
              {a.pack_size ? ` · ${a.pack_estimated ? "~" : ""}${a.pack_size} tablets` : ""}
            </span>
            {a.manufacturer && <span>by {a.manufacturer}</span>}
            {a.widely_stocked && (
              <span className="inline-flex items-center gap-1 rounded bg-sem/10 px-1.5 py-0.5 font-semibold text-sem" title="Sold by 3 or more pharmacies for this PIN">
                <Store className="h-3 w-3" /> Widely stocked
              </span>
            )}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-end gap-3">
        <BuyLink l={a} />
      </div>
      <p className="mt-2 text-[11px] text-muted">{CAUTION}</p>
    </li>
  );
}

/** Same-salt alternatives under the product: cheaper swaps first, then the other brands, then what wasn't sold online. */
export default function SwapSection({
  result,
  running,
  only,
}: {
  result: AltResult | null | undefined;
  running: boolean;
  only: (a: Alternative) => boolean;
}) {
  if (result === undefined) return running ? <div className="h-28 rounded-xl shimmer" aria-label="Looking for cheaper brands" /> : null;
  if (result === null) {
    return (
      <p className="flex items-start gap-2 rounded-xl border border-line bg-panel px-4 py-3 text-sm text-muted">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        We couldn&apos;t identify this medicine&apos;s salt, so we don&apos;t suggest other brands. We never guess on medicines.
      </p>
    );
  }
  const cheaper = result.cheaper_alternatives.filter(only);
  const others = result.other_alternatives.filter(only);
  const ref = result.reference;
  const c = result.composition;
  // not_found also lists our own searches ("Amlodipine 5mg tablet generic …"); show brand names only.
  const searched = (result.matched_brand ?? result.query).toLowerCase();
  const notSold = result.not_found.filter((n) => !/generic/i.test(n) && !n.toLowerCase().startsWith(searched));

  return (
    <section aria-labelledby="swaps-title" className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="swaps-title" className="font-semibold">{result.matched_as === "salt" ? `Brands of ${c.name}` : "Cheaper brands with the same salt"}</h2>
          <p className="text-xs text-muted">
            {c.name}
            {c.brand_count != null && ` · ${c.brand_count} brands in the index`}
          </p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs text-muted" title={result.match_reason}>
          <BadgeCheck className="h-3.5 w-3.5 text-hit" /> {result.match_reason}
        </span>
      </div>

      {ref && (
        <p className="rounded-lg bg-panel-2 px-3 py-2 text-xs text-muted">
          You searched <span className="font-medium text-ink">{result.matched_brand}</span>: best delivered at {ref.platform},{" "}
          <span className="tnum font-mono text-ink">{inr(ref.total_landed_cost)}</span>
          {ref.unit_landed_cost != null && <span className="tnum font-mono"> ({inr(ref.unit_landed_cost)} per tablet)</span>}.
        </p>
      )}

      {cheaper.length > 0 ? (
        <ul className="space-y-2">
          {cheaper.map((a) => (
            <SwapStrip key={`c-${a.brand}`} a={a} />
          ))}
        </ul>
      ) : (
        result.matched_as === "brand" && <p className="text-sm text-muted">No brand with the same salt is cheaper online right now.</p>
      )}

      {others.length > 0 && (
        <div className="surface overflow-hidden">
          <h3 className="border-b border-line bg-panel-2 px-4 py-2.5 text-sm font-semibold">
            {result.matched_as === "salt" ? "Brands" : "Other brands with the same salt"} <span className="font-normal text-muted">({others.length})</span>
          </h3>
          <ul className="divide-y divide-line">
            {others.map((a) => (
              <li key={`o-${a.brand}-${a.platform}`} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <PharmacyLogo platform={a.platform} src={a.platform_logo} />
                <span className="min-w-0 flex-1">
                  <span className="font-semibold">{a.brand}</span>{" "}
                  <span className="text-xs text-muted">
                    at {a.platform}
                    {a.manufacturer ? ` · ${a.manufacturer}` : ""}
                  </span>
                  <span className="tnum block font-mono text-xs text-muted">
                    {perUnit(a)} · {inr(a.total_landed_cost)} delivered
                  </span>
                </span>
                <BuyLink l={a} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {notSold.length > 0 && <p className="text-xs text-muted">Not sold online for this PIN right now: {notSold.join(", ")}.</p>}
      <p className="text-[11px] text-muted">{CAUTION}</p>
    </section>
  );
}
