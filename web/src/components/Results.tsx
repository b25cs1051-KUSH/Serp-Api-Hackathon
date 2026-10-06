"use client";

import { ExternalLink, MapPin, Trophy, Truck } from "lucide-react";
import { buyLink, inr, isProductLink, type Listing } from "@/lib/api";

const STATUS_STYLE: Record<Listing["delivery_status"], string> = {
  free: "text-hit",
  charged: "text-ink",
  pickup_only: "text-sem",
  unknown: "text-faint",
  unserviceable: "text-bad",
};

export default function Results({
  listings,
  query,
  pincode,
  linksResolved,
  wantLinks,
}: {
  listings: Listing[] | null;
  query: string;
  pincode: string;
  linksResolved: boolean;
  wantLinks: boolean;
}) {
  if (listings === null) {
    return (
      <div className="card p-5">
        <div className="mb-4 h-5 w-48 rounded shimmer" />
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="mb-2 h-14 rounded-lg shimmer" />
        ))}
      </div>
    );
  }

  const zone = listings[0]?.pincode_zone;

  return (
    <div className="card p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">
            {query} <span className="text-muted font-normal">· {listings.length} verified listing{listings.length === 1 ? "" : "s"}</span>
          </h3>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-muted">
            <MapPin className="h-3 w-3" /> ranked by landed price (item + delivery + platform fee) to PIN {pincode}
            {zone && <span className="rounded bg-panel-2 px-1.5 text-[10px] uppercase tracking-wide text-faint">{zone}</span>}
          </p>
        </div>
      </div>

      {listings.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">
          No listing is exactly this medicine. Look-alike products were filtered out on purpose.
        </p>
      ) : (
        <>
          {/* Phone: one card per listing */}
          <ul className="space-y-2 md:hidden">
            {listings.map((l, i) => (
              <li
                key={`${l.platform}-${l.medicine_name}-${l.price_inr}-${i}`}
                className={`rise rounded-lg border px-3 py-2.5 ${l.is_cheapest ? "border-hit/30 bg-hit/[0.04]" : "border-line"}`}
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 w-4 shrink-0">{l.is_cheapest ? <Trophy className="h-4 w-4 text-hit" /> : <span className="tnum text-xs text-faint">{i + 1}</span>}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StoreLogo l={l} />
                      <span className="font-medium">{l.platform}</span>
                      {l.is_cheapest && <span className="rounded bg-hit/15 px-1.5 text-[10px] font-semibold text-hit">CHEAPEST DELIVERED</span>}
                    </div>
                    <div className="mt-0.5 line-clamp-2 text-xs text-muted">{l.medicine_name}</div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className={`tnum font-semibold ${l.is_cheapest ? "text-hit" : ""}`}>{inr(l.total_landed_cost)}</div>
                    <div className="tnum text-[11px] text-faint">item {inr(l.price_inr)}</div>
                  </div>
                </div>
                <div className="mt-2 flex items-end justify-between gap-2 pl-6">
                  <div className="min-w-0">
                    <div className={`flex items-start gap-1 text-xs ${STATUS_STYLE[l.delivery_status]}`}>
                      <Truck className="mt-0.5 h-3 w-3 shrink-0" />
                      <span>{l.delivery_label}</span>
                    </div>
                    {l.estimated_days && <div className="mt-0.5 text-[11px] text-faint">{l.estimated_days}</div>}
                  </div>
                  <BuyButton l={l} pending={wantLinks && !linksResolved && i < 5} />
                </div>
              </li>
            ))}
          </ul>

          {/* Tablet and up: the table */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="py-2 pr-3 font-medium">#</th>
                  <th className="py-2 pr-3 font-medium">Pharmacy · product</th>
                  <th className="py-2 pr-3 text-right font-medium">Price</th>
                  <th className="py-2 pr-3 font-medium">Delivery</th>
                  <th className="py-2 pr-3 text-right font-medium">Landed</th>
                  <th className="py-2 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {listings.map((l, i) => (
                  <tr key={`${l.platform}-${l.medicine_name}-${l.price_inr}-${i}`} className={`rise border-b border-line/60 ${l.is_cheapest ? "bg-hit/[0.04]" : ""}`}>
                    <td className="py-3 pr-3 align-top">
                      {l.is_cheapest ? <Trophy className="h-4 w-4 text-hit" /> : <span className="tnum text-faint">{i + 1}</span>}
                    </td>
                    <td className="py-3 pr-3">
                      <div className="flex items-center gap-2">
                        <StoreLogo l={l} />
                        <span className="font-medium">{l.platform}</span>
                        {l.is_cheapest && <span className="rounded bg-hit/15 px-1.5 text-[10px] font-semibold text-hit">CHEAPEST DELIVERED</span>}
                      </div>
                      <div className="mt-0.5 line-clamp-1 text-xs text-muted" title={l.medicine_name}>{l.medicine_name}</div>
                    </td>
                    <td className="tnum py-3 pr-3 text-right align-top">{inr(l.price_inr)}</td>
                    <td className="py-3 pr-3 align-top">
                      <div className={`flex items-center gap-1 text-xs ${STATUS_STYLE[l.delivery_status]}`}>
                        <Truck className="h-3 w-3 shrink-0" />
                        <span className="line-clamp-1" title={l.delivery_label}>{l.delivery_label}</span>
                      </div>
                      {l.estimated_days && <div className="mt-0.5 text-[11px] text-faint">{l.estimated_days}</div>}
                    </td>
                    <td className={`tnum py-3 pr-3 text-right align-top font-semibold ${l.is_cheapest ? "text-hit" : ""}`}>{inr(l.total_landed_cost)}</td>
                    <td className="py-3 text-right align-top">
                      <BuyButton l={l} pending={wantLinks && !linksResolved && i < 5} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function StoreLogo({ l }: { l: Listing }) {
  return l.platform_logo ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={l.platform_logo} alt="" className="h-5 w-5 shrink-0 rounded" />
  ) : (
    <span className="h-5 w-5 shrink-0 rounded bg-panel-2" />
  );
}

/** The listing's product page (or the store search when none is known); a shimmer while top links resolve. */
function BuyButton({ l, pending }: { l: Listing; pending: boolean }) {
  if (pending) return <span className="inline-block h-7 w-20 shrink-0 rounded-md shimmer" title="Resolving the pharmacy's own product page…" />;
  const direct = isProductLink(l);
  return (
    <a
      href={buyLink(l)}
      target="_blank"
      rel="noopener noreferrer"
      title={direct ? "Pharmacy product page" : "Pharmacy search page (direct link not resolved)"}
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium ring-1 transition ${
        direct ? "bg-hit/10 text-hit ring-hit/30 hover:bg-hit/20" : "text-muted ring-line hover:text-ink"
      }`}
    >
      {direct ? "Visit site" : "Search"} <ExternalLink className="h-3 w-3" />
    </a>
  );
}
