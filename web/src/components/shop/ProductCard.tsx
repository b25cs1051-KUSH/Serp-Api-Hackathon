"use client";

import { ExternalLink, Info, Truck } from "lucide-react";
import PharmacyLogo from "@/components/PharmacyLogo";
import { buyLink, inr, isProductLink, type Alternative, type Listing } from "@/lib/api";

const STATUS_TEXT: Record<Listing["delivery_status"], string> = {
  free: "text-hit",
  charged: "text-miss",
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
      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white shadow-sm hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      {label ?? (direct ? "Visit site" : "Search")} <ExternalLink className="h-3.5 w-3.5" />
    </a>
  );
}

/** The searched medicine's best delivered offer: pharmacy logo and price on the left, the medicine on the right. */
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
  const lowestShelf = listings.reduce((a, b) => (b.price_inr < a.price_inr ? b : a));
  const shelfTrap =
    lowestShelf !== best &&
    best.total_landed_cost != null &&
    lowestShelf.total_landed_cost != null &&
    lowestShelf.total_landed_cost > best.total_landed_cost;

  return (
    <article className="rise surface overflow-hidden" aria-label={name}>
      <div className="flex flex-col sm:flex-row">
        <div className="flex items-center gap-3 border-b border-hit/30 bg-hit/[0.08] px-5 py-4 sm:w-64 sm:shrink-0 sm:flex-col sm:items-start sm:justify-center sm:border-b-0 sm:border-r">
          <div className="flex items-center gap-2">
            <PharmacyLogo platform={best.platform} src={best.platform_logo} size="lg" />
            <span className="font-semibold">{best.platform}</span>
          </div>
          <div className="ml-auto text-right sm:ml-0 sm:text-left">
            <div className="tnum font-mono text-3xl font-bold text-hit">{inr(best.total_landed_cost)}</div>
            <div className="text-xs font-medium text-muted">delivered to your door</div>
          </div>
        </div>

        <div className="min-w-0 flex-1 p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-hit px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">Best offer</span>
            {best.delivery_status === "free" && (
              <span className="rounded bg-hit/12 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-hit ring-1 ring-hit/30">Free delivery</span>
            )}
          </div>
          <h2 className="mt-1.5 text-xl font-bold tracking-tight">{name}</h2>
          <p className="line-clamp-2 text-sm text-muted">
            {best.manufacturer ? `${best.manufacturer} · ` : ""}
            {best.medicine_name}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className={`flex items-center gap-1.5 font-medium ${STATUS_TEXT[best.delivery_status]}`}>
              <Truck className="h-4 w-4 shrink-0" /> {best.delivery_label}
            </span>
            {best.estimated_days && <span className="text-muted">arrives in {best.estimated_days}</span>}
            <span className="tnum text-muted">item {inr(best.price_inr)}</span>
            {reference?.unit_landed_cost != null && (
              <span className="tnum font-semibold" title={reference.pack_estimated ? "Pack size estimated" : undefined}>
                {reference.pack_estimated ? "~" : ""}
                {inr(reference.unit_landed_cost)}/tablet
              </span>
            )}
          </div>

          {shelfTrap && (
            <p className="mt-3 flex items-start gap-2 rounded-lg border border-[#f59e0b]/50 bg-[#fef3c7] px-3 py-2 text-xs text-[#713f12]">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Lowest shelf price is {inr(lowestShelf.price_inr)} at {lowestShelf.platform}, but it costs {inr(lowestShelf.total_landed_cost)} with delivery.
            </p>
          )}

          <div className="mt-4 flex justify-end">
            <BuyLink l={best} pending={pending(best)} label={isProductLink(best) ? `Buy at ${best.platform}` : undefined} />
          </div>
        </div>
      </div>
    </article>
  );
}
