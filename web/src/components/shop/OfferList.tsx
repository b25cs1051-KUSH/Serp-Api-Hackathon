"use client";

import { ChevronDown, ExternalLink, Trophy, Truck } from "lucide-react";
import { useState } from "react";
import PharmacyLogo from "@/components/PharmacyLogo";
import { buyLink, inr, isProductLink, type Listing } from "@/lib/api";
import { byPrice, deliverable, type Offer } from "@/lib/offers";

/** Delivery text colour: green free, amber charged, red when it can't be delivered or the fee is unknown. */
const DELIVERY_TONE: Record<Listing["delivery_status"], string> = {
  free: "text-hit",
  charged: "text-miss",
  pickup_only: "text-bad",
  unknown: "text-bad",
  unserviceable: "text-bad",
};

function Badge({ tone, children }: { tone: "green" | "lightgreen" | "yellow" | "red" | "blue"; children: React.ReactNode }) {
  const cls = {
    green: "bg-hit/12 text-hit ring-hit/30",
    lightgreen: "bg-emerald-100 text-emerald-800 ring-emerald-300",
    yellow: "bg-[#fde68a] text-[#713f12] ring-[#f59e0b]/50",
    red: "bg-bad text-white ring-bad",
    blue: "bg-sem/10 text-sem ring-sem/30",
  }[tone];
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ring-1 ${cls}`}>{children}</span>;
}

/** "Visit site" for a product page, "Search" for a pharmacy search page; a shimmer while the page is being found. */
export function VisitButton({ l, pending }: { l: Listing; pending?: boolean }) {
  if (pending) return <span className="inline-block h-8 w-24 shrink-0 rounded-lg shimmer" title="Finding the pharmacy's own product page…" />;
  const href = buyLink(l);
  if (!href) return null;
  const direct = isProductLink(l);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={direct ? "Opens the pharmacy's product page" : "Opens the pharmacy's search (no product page found)"}
      className={`inline-flex shrink-0 items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
        direct ? "bg-accent text-white hover:brightness-110" : "border border-line bg-panel text-ink hover:border-accent/60"
      }`}
    >
      {direct ? "Visit site" : "Search"} <ExternalLink aria-hidden className="h-3.5 w-3.5" />
    </a>
  );
}

function PerTablet({ o }: { o: Offer }) {
  if (o.perTablet == null) return <span className="text-xs text-faint">—</span>;
  return (
    <span className="tnum font-mono text-sm font-semibold" title={o.perTabletEstimated ? "Pack size estimated" : undefined}>
      {o.perTabletEstimated ? "~" : ""}
      {inr(o.perTablet)}
    </span>
  );
}

function Badges({ o, cheapest }: { o: Offer; cheapest: boolean }) {
  return (
    <>
      {cheapest && <Badge tone="yellow">Cheapest</Badge>}
      {o.isSwap && <Badge tone="lightgreen">Same salt</Badge>}
      {o.savingsPct != null && o.savingsPct > 0 && <Badge tone="red">−{Math.round(o.savingsPct)}%</Badge>}
      {o.listing.delivery_status === "free" && <Badge tone="green">Free delivery</Badge>}
    </>
  );
}

/** Ranked offers: rank, pharmacy, product, per-tablet price, delivery, what you pay, and the pharmacy's page. */
const PAGE = 10;

export default function OfferList({ offers: all, pending, framed = true }: { offers: Offer[]; pending?: (l: Listing) => boolean; framed?: boolean }) {
  // Long lists open 10 at a time, so the next medicine is never far below.
  const [visible, setVisible] = useState(PAGE);
  const offers = all.slice(0, visible);
  const left = all.length - offers.length;
  // The cheapest deliverable offer, whatever order the list is in (e.g. sorted by delivery speed).
  const cheapestKey = [...all].filter(deliverable).sort(byPrice)[0]?.key;
  return (
    <>
      {/* Phone: one card per offer */}
      <ul className="space-y-2 md:hidden">
        {offers.map((o, i) => {
          const l = o.listing;
          const top = o.key === cheapestKey;
          return (
            <li key={o.key} className={`rounded-xl border bg-panel px-3 py-3 ${top ? "border-amber-400 ring-1 ring-amber-300" : o.isSwap ? "border-emerald-200" : "border-line"}`}>
              <div className="flex items-start gap-2.5">
                <PharmacyLogo platform={l.platform} src={l.platform_logo} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-semibold">{o.isSwap ? o.brand : l.platform}</span>
                    <Badges o={o} cheapest={top} />
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-muted">{o.isSwap ? `${l.platform} · ${l.medicine_name}` : l.medicine_name}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className={`tnum font-mono text-base font-bold ${top ? "text-hit" : ""}`}>{inr(l.total_landed_cost)}</div>
                  <div className="text-[11px] text-muted">
                    <PerTablet o={o} />/tab
                  </div>
                </div>
              </div>
              <div className="mt-2 flex items-end justify-between gap-2 pl-9">
                <div className={`flex items-start gap-1 text-xs ${DELIVERY_TONE[l.delivery_status]}`}>
                  <Truck aria-hidden className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>
                    {l.delivery_label}
                    {l.estimated_days && <span className="text-muted"> · {l.estimated_days}</span>}
                  </span>
                </div>
                <VisitButton l={l} pending={pending?.(l)} />
              </div>
              <span className="sr-only">Rank {i + 1}</span>
            </li>
          );
        })}
      </ul>

      {/* Tablet and up: the table */}
      <div className={`hidden overflow-x-auto bg-panel md:block ${framed ? "rounded-xl border border-line" : ""}`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line bg-panel-2 text-left text-[11px] uppercase tracking-wider text-muted">
              <th className="py-2.5 pl-4 pr-2 font-semibold">#</th>
              <th className="py-2.5 pr-3 font-semibold">Pharmacy · product</th>
              <th className="py-2.5 pr-3 text-right font-semibold">Per tablet</th>
              <th className="py-2.5 pr-3 font-semibold">Delivery</th>
              <th className="py-2.5 pr-3 text-right font-semibold">You pay</th>
              <th className="py-2.5 pr-4" />
            </tr>
          </thead>
          <tbody>
            {offers.map((o, i) => {
              const l = o.listing;
              const top = o.key === cheapestKey;
              return (
                <tr key={o.key} className={`border-b border-line/70 last:border-0 ${top ? "bg-amber-50" : o.isSwap ? "bg-emerald-50/60" : ""}`}>
                  <td className="py-3 pl-4 pr-2 align-top">
                    {top ? <Trophy aria-label="Cheapest" className="h-4 w-4 text-amber-500" /> : <span className="tnum text-muted">{i + 1}</span>}
                  </td>
                  <td className="py-3 pr-3">
                    <div className="flex items-start gap-2.5">
                      <PharmacyLogo platform={l.platform} src={l.platform_logo} />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-semibold">{o.isSwap ? o.brand : l.platform}</span>
                          {o.isSwap && <span className="text-xs text-muted">at {l.platform}</span>}
                          <Badges o={o} cheapest={top} />
                        </div>
                        <div className="mt-0.5 line-clamp-1 text-xs text-muted" title={l.medicine_name}>
                          {l.manufacturer ? `${l.manufacturer} · ` : ""}
                          {l.medicine_name}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 pr-3 text-right align-top">
                    <PerTablet o={o} />
                  </td>
                  <td className="py-3 pr-3 align-top">
                    <div className={`flex items-start gap-1 text-xs font-medium ${DELIVERY_TONE[l.delivery_status]}`}>
                      <Truck aria-hidden className="mt-0.5 h-3 w-3 shrink-0" />
                      <span className="line-clamp-2" title={l.delivery_label}>{l.delivery_label}</span>
                    </div>
                    {l.estimated_days && <div className="mt-0.5 text-[11px] text-muted">{l.estimated_days}</div>}
                  </td>
                  <td className={`tnum py-3 pr-3 text-right align-top font-mono text-base font-bold ${top ? "text-hit" : ""}`}>{inr(l.total_landed_cost)}</td>
                  <td className="py-3 pr-4 text-right align-top">
                    <VisitButton l={l} pending={pending?.(l)} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {left > 0 && (
        <button
          type="button"
          onClick={() => setVisible((v) => v + PAGE)}
          className={`flex w-full items-center justify-center gap-1.5 border-line bg-panel-2 py-2.5 text-sm font-semibold text-accent hover:bg-accent/10 focus-visible:outline-2 focus-visible:outline-accent ${
            framed ? "mt-2 rounded-xl border" : "mt-2 rounded-xl border md:mt-0 md:rounded-none md:border-0 md:border-t"
          }`}
        >
          <ChevronDown aria-hidden className="h-4 w-4" />
          More options · show {Math.min(PAGE, left)} more{left > PAGE ? ` (${left} left)` : ""}
        </button>
      )}
    </>
  );
}
