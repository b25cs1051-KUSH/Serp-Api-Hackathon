"use client";

import { ChevronDown, Store, Trophy, Truck } from "lucide-react";
import { useState, type ReactNode } from "react";
import PharmacyLogo from "@/components/PharmacyLogo";
import { inr, type Alternative, type Listing } from "@/lib/api";
import { byPrice, deliverable, type Offer } from "@/lib/offers";
import { Badge, DELIVERY_TONE, PerTablet, VisitButton } from "./OfferList";

const PAGE = 10;

/**
 * One column of offers under the best-offer card: the searched medicine at every pharmacy, or the alternative
 * medicines. Cards, cheapest per tablet first, each with the description, delivery, what you pay and the pharmacy's page.
 */
export default function OfferColumn({
  id,
  title,
  sub,
  offers: unsorted,
  empty,
  pending,
  children,
}: {
  id: string;
  title: string;
  sub?: ReactNode;
  offers: Offer[];
  empty: string;
  pending?: (l: Listing) => boolean;
  children?: ReactNode;
}) {
  const [visible, setVisible] = useState(PAGE);
  const all = [...unsorted].sort(byPrice);
  const offers = all.slice(0, visible);
  const left = all.length - offers.length;
  const cheapestKey = all.find(deliverable)?.key;

  return (
    <section aria-labelledby={id} className="surface flex min-w-0 flex-col overflow-hidden">
      <header className="border-b border-line bg-panel-2 px-4 py-3">
        <h2 id={id} className="text-base font-bold">
          {title} <span className="font-normal text-muted">· {all.length}</span>
        </h2>
        {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
      </header>

      {all.length === 0 ? (
        <p className="m-3 rounded-xl border border-dashed border-line p-5 text-center text-sm text-muted">{empty}</p>
      ) : (
        <ul className="space-y-2 p-3">
          {offers.map((o, i) => (
            <OfferCard key={o.key} o={o} rank={i + 1} top={o.key === cheapestKey} pending={pending?.(o.listing)} />
          ))}
        </ul>
      )}

      {left > 0 && (
        <button
          type="button"
          onClick={() => setVisible((v) => v + PAGE)}
          className="mx-3 mb-3 flex items-center justify-center gap-1.5 rounded-xl border border-line bg-panel-2 py-2.5 text-sm font-semibold text-accent hover:bg-accent/10 focus-visible:outline-2 focus-visible:outline-accent"
        >
          <ChevronDown aria-hidden className="h-4 w-4" />
          More options · show {Math.min(PAGE, left)} more{left > PAGE ? ` (${left} left)` : ""}
        </button>
      )}
      {children && <div className="mt-auto space-y-1.5 border-t border-line px-4 py-3 text-xs text-muted">{children}</div>}
    </section>
  );
}

function OfferCard({ o, rank, top, pending }: { o: Offer; rank: number; top: boolean; pending?: boolean }) {
  const l = o.listing;
  const alt = o.isSwap ? (l as Alternative) : null;
  return (
    <li className={`rounded-xl border bg-panel px-3 py-3 ${top ? "border-amber-400 bg-amber-50 ring-1 ring-amber-300" : "border-line"}`}>
      <div className="flex items-start gap-2.5">
        <span className="mt-1 w-4 shrink-0 text-center">
          {top ? <Trophy aria-label="Cheapest" className="h-4 w-4 text-amber-500" /> : <span className="tnum text-xs text-muted">{rank}</span>}
        </span>
        <PharmacyLogo platform={l.platform} src={l.platform_logo} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold">{alt ? alt.brand : l.platform}</span>
            {alt && <span className="text-xs text-muted">at {l.platform}</span>}
            {top && <Badge tone="yellow">Cheapest</Badge>}
            {o.savingsPct != null && o.savingsPct > 0 && (
              <Badge tone="red">
                −{alt?.estimated ? "≈" : ""}
                {Math.round(o.savingsPct)}%
              </Badge>
            )}
            {l.delivery_status === "free" && <Badge tone="green">Free delivery</Badge>}
            {alt?.widely_stocked && (
              <span title="Sold by 3 or more pharmacies for this PIN">
                <Badge tone="blue">
                  <Store aria-hidden className="mr-0.5 h-3 w-3" /> Widely stocked
                </Badge>
              </span>
            )}
          </div>
          <div className="mt-0.5 line-clamp-2 text-xs text-muted" title={l.medicine_name}>
            {l.manufacturer ? `${l.manufacturer} · ` : ""}
            {l.medicine_name}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className={`tnum font-mono text-base font-bold ${top ? "text-hit" : ""}`}>{inr(l.total_landed_cost)}</div>
          <div className="text-[11px] text-muted">you pay</div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 pl-16 text-[11px] text-muted">
        <span>
          <PerTablet o={o} />
          /tablet
        </span>
        <span className="tnum">item {inr(l.price_inr)}</span>
        {alt?.pack_size ? <span>{alt.pack_estimated ? `~${alt.pack_size} tablets (estimated)` : `${alt.pack_size} tablets`}</span> : null}
        {alt && o.savingsPct != null && alt.savings != null && (
          <span className="font-semibold text-hit">
            saves {inr(alt.savings)}
            {alt.price_basis === "per_tablet" ? "/tablet" : ""}
          </span>
        )}
      </div>

      <div className="mt-2 flex items-end justify-between gap-2 pl-16">
        <div className={`flex items-start gap-1 text-xs font-medium ${DELIVERY_TONE[l.delivery_status]}`}>
          <Truck aria-hidden className="mt-0.5 h-3 w-3 shrink-0" />
          <span>
            {l.delivery_label}
            {l.estimated_days && <span className="font-normal text-muted"> · {l.estimated_days}</span>}
          </span>
        </div>
        <VisitButton l={l} pending={pending} />
      </div>
    </li>
  );
}
