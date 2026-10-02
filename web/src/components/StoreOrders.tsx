"use client";

import { Check, ClipboardCopy, ExternalLink, Store, Truck } from "lucide-react";
import { useState } from "react";
import { buyLink, inr, type BasketPlan, type BasketStore, type RxItem } from "@/lib/api";

/** The chosen plan as orders: one card per pharmacy, with every product page and a shopping list. */
export default function StoreOrders({ plan, items }: { plan: BasketPlan; items: RxItem[] }) {
  return (
    <div className="space-y-3">
      {plan.stores.map((s) => (
        <StoreOrder key={s.platform} store={s} items={items} />
      ))}
      <p className="px-1 text-xs text-faint">
        Pharmacies don&apos;t let other sites fill their carts. The open button takes you through each product page in turn, one
        tab per click; add the quantity shown on each.
      </p>
    </div>
  );
}

function StoreOrder({ store, items }: { store: BasketStore; items: RxItem[] }) {
  const [copied, setCopied] = useState(false);
  const [opened, setOpened] = useState(0);
  const links = store.lines.flatMap((o) => {
    const href = buyLink(o);
    return href ? [{ brand: o.brand, href }] : [];
  });
  const step = opened < links.length ? opened : 0; // the plan may change under us
  const next = links[step];
  const list = [
    `${store.platform}:`,
    ...store.lines.map(
      (o) => `- ${o.brand} × ${o.packs} pack${o.packs === 1 ? "" : "s"} (${o.packs * o.pack_size} tablets) ${inr(o.item_cost)}`,
    ),
    `Total ${inr(store.total)}${store.fee > 0 ? ` incl. ${inr(store.fee)} delivery` : ", free delivery"}`,
  ].join("\n");

  const copy = () => {
    navigator.clipboard?.writeText(list).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => undefined,
    );
  };

  return (
    <div className="rise card p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Store className="h-4 w-4 text-hit" />
          <h3 className="font-semibold">{store.platform}</h3>
          <span className={`flex items-center gap-1 text-xs ${store.free_delivery ? "text-hit" : "text-miss"}`}>
            <Truck className="h-3 w-3" /> {store.free_delivery ? "free delivery" : `${inr(store.fee)} delivery`}
          </span>
        </div>
        <div className="tnum text-sm">
          <span className="text-muted">
            {inr(store.subtotal)}
            {store.fee > 0 && ` + ${inr(store.fee)}`} ={" "}
          </span>
          <span className="font-semibold">{inr(store.total)}</span>
        </div>
      </div>

      <div className="space-y-2">
        {store.lines.map((o) => {
          const href = buyLink(o);
          return (
            <div key={o.line} className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel-2 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{o.brand}</span>
                  {!o.prescribed && (
                    <span className="rounded bg-hit/15 px-1.5 py-0.5 text-[10px] font-semibold text-hit">
                      SWAP for {items[o.line]?.q ?? "this medicine"}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 line-clamp-1 text-xs text-faint" title={o.medicine_name}>
                  {o.manufacturer ? `${o.manufacturer} · ` : ""}
                  <span className="text-muted">
                    {o.packs} pack{o.packs === 1 ? "" : "s"} × {o.pack_estimated ? "~" : ""}
                    {o.pack_size} tablets
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="tnum font-mono text-sm font-semibold">{inr(o.item_cost)}</div>
                <div className="tnum text-[11px] text-muted">
                  {o.pack_estimated ? "~" : ""}
                  {inr(o.per_tablet)}/tablet
                </div>
              </div>
              {href && (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded-md bg-hit/10 px-2.5 py-1.5 text-xs font-medium text-hit ring-1 ring-hit/30 hover:bg-hit/20"
                >
                  Buy <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {next && (
          <button
            type="button"
            onClick={() => {
              // One tab per click: browsers block every extra tab opened by a single click.
              const w = window.open(next.href, "_blank");
              if (w) w.opener = null;
              setOpened((step + 1) % links.length);
            }}
            className="flex items-center gap-1.5 rounded-lg bg-hit px-3 py-2 text-sm font-semibold text-bg hover:brightness-110"
          >
            <ExternalLink className="h-4 w-4" /> Open {next.brand}
            {links.length > 1 && <span className="font-normal opacity-80">({step + 1} of {links.length})</span>}
          </button>
        )}
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-sm text-ink hover:border-hit/50"
        >
          {copied ? <Check className="h-4 w-4 text-hit" /> : <ClipboardCopy className="h-4 w-4" />}
          {copied ? "Copied" : "Copy shopping list"}
        </button>
      </div>
    </div>
  );
}
