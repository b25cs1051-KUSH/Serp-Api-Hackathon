"use client";

import { AlertTriangle, Pill } from "lucide-react";
import { inr, type RxItem, type RxLine } from "@/lib/api";
import { buildOffers, byPrice, deliverable } from "@/lib/offers";
import OfferList from "./OfferList";

/**
 * Every medicine of the prescription with every place to buy it: the prescribed brand at each pharmacy and
 * each same-salt brand, cheapest per tablet first, with the pharmacy's page.
 */
export default function MedicineSources({ lines, items }: { lines: Record<number, RxLine>; items: RxItem[] }) {
  return (
    <section aria-labelledby="sources-title" className="space-y-4">
      <div>
        <h3 id="sources-title" className="text-xl font-extrabold tracking-tight">Medicine by medicine</h3>
        <p className="text-sm text-muted">Every place to buy each medicine, cheapest per tablet first (delivery included when bought on its own).</p>
      </div>
      {items.map((it, i) => {
        const line = lines[i];
        const name = line?.alternatives?.matched_brand ?? it.q;
        const offers = line ? buildOffers(name, line.listings ?? [], line.alternatives).sort(byPrice) : [];
        const best = offers.find(deliverable);
        return (
          <article key={i} className="surface overflow-hidden" aria-label={it.q}>
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-panel-2 px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/10 text-accent">
                  <Pill aria-hidden className="h-4 w-4" />
                </span>
                <div>
                  <h4 className="font-bold">{it.q}</h4>
                  <p className="text-xs text-muted">
                    {line?.tablets ? `${line.tablets} ${line.tablets_how === "items" || line.tablets_how === "one item" ? "items" : "tablets"}` : "1 pack"}
                    {line?.alternatives?.composition ? ` · ${line.alternatives.composition.name}` : ""}
                    {offers.length ? ` · ${offers.length} offers` : ""}
                  </p>
                </div>
              </div>
              {best?.perTablet != null && (
                <span className="rounded-lg bg-hit px-2.5 py-1 text-xs font-bold text-white">
                  From {best.perTabletEstimated ? "~" : ""}
                  {inr(best.perTablet)}/tablet
                </span>
              )}
            </header>
            {line?.status === "choose" ? (
              <p className="px-4 py-3 text-sm text-sem">Needs a strength: pick one above.</p>
            ) : !line || line.status !== "done" ? (
              <div className="m-4 h-16 rounded-lg shimmer" aria-label="Searching" />
            ) : offers.length === 0 ? (
              <p className="flex items-center gap-2 px-4 py-3 text-sm font-medium text-bad">
                <AlertTriangle className="h-4 w-4" /> Not sold online for this PIN right now.
              </p>
            ) : (
              <div className="p-3 md:p-0">
                <OfferList offers={offers} framed={false} />
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}
