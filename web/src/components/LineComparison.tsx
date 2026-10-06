"use client";

import { ArrowRight } from "lucide-react";
import { inr, type BasketResult, type RxItem, type RxLine } from "@/lib/api";

type Offer = BasketResult["per_line"][number]["cheapest_prescribed"];

/** Each medicine: the prescribed brand's cheapest offer next to the cheapest same-salt brand. */
export default function LineComparison({
  basket,
  lines,
  items,
}: {
  basket: BasketResult;
  lines: Record<number, RxLine>;
  items: RxItem[];
}) {
  const byLine = new Map(basket.per_line.map((p) => [p.line, p]));
  return (
    <div className="card p-5">
      <h3 className="font-semibold">Medicine by medicine</h3>
      <p className="mt-0.5 text-xs text-faint">
        Item prices for the quantity needed; delivery is counted per order in the plans above.
      </p>
      <div className="mt-3 hidden grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_1.25rem_minmax(0,1.3fr)] gap-3 px-3 text-[11px] uppercase tracking-wider text-faint md:grid">
        <span>Medicine</span>
        <span>As prescribed</span>
        <span />
        <span>Cheapest same salt</span>
      </div>
      <div className="mt-1 space-y-2">
        {items.map((it, i) => {
          const p = byLine.get(i);
          const l = lines[i];
          const pres = p?.cheapest_prescribed ?? null;
          const any = p?.cheapest_any ?? null;
          const isSwap = any && pres && any.brand !== pres.brand;
          const saving = isSwap && pres && any ? 1 - any.per_tablet / pres.per_tablet : 0;
          return (
            <div
              key={i}
              className="grid gap-2 rounded-lg border border-line bg-panel-2 px-3 py-2.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_1.25rem_minmax(0,1.3fr)] md:items-center md:gap-3"
            >
              <div>
                <div className="font-medium">{it.q}</div>
                <div className="text-[11px] text-faint">
                  {p?.tablets
                    ? p.tablets_how === "items" || p.tablets_how === "one item"
                      ? `${p.tablets} item${p.tablets === 1 ? "" : "s"}`
                      : `${p.tablets} tablets${p.tablets_how === "one pack" ? " (1 pack)" : ""}`
                    : ""}
                </div>
              </div>
              {l?.status === "choose" ? (
                <div className="text-sm text-sem md:col-span-3">Needs a strength: pick one above.</div>
              ) : !p || (!pres && !any) ? (
                <div className="text-sm text-miss md:col-span-3">Not sold online for this PIN right now.</div>
              ) : (
                <>
                  <OfferCell offer={pres} empty="Prescribed brand not sold online here" />
                  <ArrowRight className="hidden h-4 w-4 text-faint md:block" />
                  <OfferCell
                    offer={isSwap ? any : null}
                    empty={pres ? "The prescribed brand is already the cheapest" : "—"}
                    highlight
                    badge={saving > 0.005 ? `−${Math.round(saving * 100)}% per tablet` : undefined}
                  />
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function OfferCell({ offer, empty, highlight, badge }: { offer: Offer; empty: string; highlight?: boolean; badge?: string }) {
  if (!offer) return <div className="text-xs text-faint">{empty}</div>;
  return (
    <div className={highlight ? "rounded-md bg-hit/[0.07] px-2 py-1" : ""}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={`font-medium ${highlight ? "text-hit" : ""}`}>{offer.brand}</span>
        {badge && <span className="rounded bg-hit px-1.5 text-[10px] font-semibold text-bg">{badge}</span>}
      </div>
      <div className="tnum text-[11px] text-muted">
        {offer.platform} · {inr(offer.item_cost)} · {offer.pack_estimated ? "~" : ""}
        {inr(offer.per_tablet)}
        {offer.unit === "item" ? " each" : "/tablet"}
      </div>
    </div>
  );
}
