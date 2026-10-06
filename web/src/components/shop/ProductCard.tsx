"use client";

import { ExternalLink, Info, Truck } from "lucide-react";
import PharmacyLogo from "@/components/PharmacyLogo";
import { buyLink, inr, isProductLink, type Alternative, type Listing } from "@/lib/api";

const STATUS_TEXT: Record<Listing["delivery_status"], string> = {
  free: "text-hit",
  charged: "text-ink",
  pickup_only: "text-sem",
  unknown: "text-faint",
  unserviceable: "text-bad",
};

export const delivered = (l: Listing) => l.delivery_status === "free" || l.delivery_status === "charged";

/** "Visit site" (the product page) or "Search" (the store's search, when no product page is known); a shimmer while it resolves. */
export function BuyLink({ l, pending, label }: { l: Listing; pending?: boolean; label?: string }) {
  if (pending) return <span className="inline-block h-9 w-24 shrink-0 rounded-lg shimmer" title="Finding the pharmacy's own product page…" />;
  const direct = isProductLink(l);
  return (
    <a
      href={buyLink(l)}
      target="_blank"
      rel="noopener noreferrer"
      title={direct ? "Opens the pharmacy's product page" : "Opens the pharmacy's search (no product page found)"}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-2 text-sm font-medium hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-accent"
    >
      {label ?? (direct ? "Visit site" : "Search")} <ExternalLink className="h-3.5 w-3.5" />
    </a>
  );
}

/** One product: its best delivered offer, its Buy link and the other pharmacies as chips. */
export default function ProductCard({
  name,
  listings,
  reference,
  pending,
}: {
  name: string;
  listings: Listing[];
  reference: Alternative | null | undefined;
  pending: (l: Listing) => boolean;
}) {
  const best = listings.find(delivered) ?? listings[0];
  if (!best) return null;
  const others = listings.filter((l) => l !== best);
  const lowestShelf = listings.reduce((a, b) => (b.price_inr < a.price_inr ? b : a));
  const shelfTrap =
    lowestShelf !== best &&
    best.total_landed_cost != null &&
    lowestShelf.total_landed_cost != null &&
    lowestShelf.total_landed_cost > best.total_landed_cost;

  return (
    <article className="rise surface p-4 sm:p-5" aria-label={name}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">{name}</h2>
          <p className="line-clamp-2 text-sm text-muted">
            {best.manufacturer ? `${best.manufacturer} · ` : ""}
            {best.medicine_name}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <PharmacyLogo platform={best.platform} src={best.platform_logo} size="lg" />
          <div className="text-right">
            <div className="tnum font-mono text-2xl font-semibold">{inr(best.total_landed_cost)}</div>
            <div className="text-xs text-muted">delivered, at <span className="font-semibold text-ink">{best.platform}</span></div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className={`flex items-center gap-1.5 ${STATUS_TEXT[best.delivery_status]}`}>
          <Truck className="h-4 w-4 shrink-0" /> {best.delivery_label}
        </span>
        {best.estimated_days && <span className="text-muted">arrives in {best.estimated_days}</span>}
        <span className="tnum text-muted">item {inr(best.price_inr)}</span>
        {reference?.unit_landed_cost != null && (
          <span className="tnum text-muted" title={reference.pack_estimated ? "Pack size estimated" : undefined}>
            {reference.pack_estimated ? "~" : ""}
            {inr(reference.unit_landed_cost)}/tablet at {reference.platform}
          </span>
        )}
      </div>

      {shelfTrap && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-panel-2 px-3 py-2 text-xs text-muted">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          The lowest shelf price, {inr(lowestShelf.price_inr)} at {lowestShelf.platform}, comes to {inr(lowestShelf.total_landed_cost)} once delivery is added.
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
        <BuyLink l={best} pending={pending(best)} label={isProductLink(best) ? `Buy at ${best.platform}` : undefined} />
      </div>

      {others.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Also at</div>
          <ul className="flex flex-wrap gap-2">
            {others.map((l, i) => (
              <li key={`${l.platform}-${l.medicine_name}-${l.price_inr}-${i}`}>
                <a
                  href={buyLink(l)}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={`${l.medicine_name} · ${l.delivery_label}${l.estimated_days ? ` · ${l.estimated_days}` : ""}`}
                  className="flex items-center gap-1.5 rounded-full border border-line bg-panel-2 py-1 pl-1 pr-3 text-xs hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-accent"
                >
                  <PharmacyLogo platform={l.platform} src={l.platform_logo} size="sm" />
                  <span className="font-medium">{l.platform}</span>
                  <span className={`tnum font-mono ${delivered(l) ? "" : STATUS_TEXT[l.delivery_status]}`}>
                    {l.total_landed_cost != null ? inr(l.total_landed_cost) : inr(l.price_inr)}
                    {l.delivery_status === "pickup_only" ? " · pickup only" : l.delivery_status === "unknown" ? " + delivery fee not published" : l.delivery_status === "unserviceable" ? " · no delivery here" : ""}
                  </span>
                  {pending(l) && <span className="h-2 w-2 rounded-full shimmer" aria-hidden />}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
