"use client";

import { AlertTriangle, ArrowRightLeft, ExternalLink, Pill as PillIcon, ShoppingCart, Stethoscope, Store, Truck } from "lucide-react";
import { useState } from "react";
import { buyLink, inr, type BasketPlan, type BasketResult, type RxItem, type RxLine } from "@/lib/api";

type Mode = "with_swaps" | "as_prescribed";

/** The cheapest way to buy the whole prescription, delivery included. */
export default function BasketCard({
  basket,
  lines,
  items,
  running,
  onPick,
}: {
  basket: BasketResult | null;
  lines: Record<number, RxLine>;
  items: RxItem[];
  running: boolean;
  onPick: (line: number, query: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("with_swaps");
  const skipped = Object.values(lines).filter((l) => l.status === "choose");

  if (!basket) {
    return (
      <div className="space-y-3">
        {skipped.map((l) => <ChooseLine key={l.line} line={l} onPick={onPick} />)}
        <div className="card p-5">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-faint">Searching every medicine at once</div>
          <div className="space-y-2">
            {items.map((it, i) => {
              const l = lines[i];
              const state = !l ? "searching" : l.status === "choose" ? "needs a strength" : l.status === "main" ? "comparing brands" : "done";
              return (
                <div key={i} className="flex items-center justify-between gap-3 rounded-lg border border-line bg-panel-2 px-3 py-2 text-sm">
                  <span className="truncate">{it.q}</span>
                  <span className={`shrink-0 text-xs ${state === "done" ? "text-hit" : state === "needs a strength" ? "text-sem" : "text-muted"}`}>
                    {state === "searching" || state === "comparing brands" ? <span className="shimmer inline-block h-3 w-20 rounded" /> : state}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  const plan = basket[mode].best;
  const alt = basket[mode].single_store;
  const showSingle = alt && plan && (alt.stores[0]?.platform !== plan.stores[0]?.platform || plan.stores.length > 1);
  const name = (i: number) => items[i]?.q ?? lines[i]?.query ?? `Medicine ${i + 1}`;

  return (
    <div className="space-y-3">
      {skipped.map((l) => <ChooseLine key={l.line} line={l} onPick={onPick} />)}

      {/* Headline */}
      <div className="rise overflow-hidden rounded-2xl border border-hit/40 bg-hit/[0.06]">
        <div className="flex flex-wrap items-start justify-between gap-4 p-6">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">
              {mode === "with_swaps" ? "Cheapest basket, delivered" : "Your prescribed brands, delivered"}
            </div>
            {plan ? (
              <>
                <div className="mt-2 text-3xl font-semibold tracking-tight">
                  <span className="tnum">{inr(plan.total)}</span>{" "}
                  <span className="text-base font-normal text-muted">for {countLines(plan)} medicine{countLines(plan) === 1 ? "" : "s"}</span>
                </div>
                <p className="mt-1 text-sm text-muted">
                  {plan.stores.length === 1
                    ? `One order at ${plan.stores[0].platform}`
                    : `${plan.stores.length} orders: ${plan.stores.map((s) => s.platform).join(" + ")}`}
                  {" · "}
                  {plan.fees_total === 0 ? "free delivery" : `${inr(plan.fees_total)} delivery`}
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm text-muted">None of these medicines could be priced for delivery to this PIN.</p>
            )}
            {mode === "with_swaps" && basket.saving != null && basket.saving > 0 && (
              <p className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-hit/15 px-3 py-1.5 text-sm font-medium text-hit">
                <ArrowRightLeft className="h-4 w-4" />
                {inr(basket.saving)} less than the prescribed brands
                {basket.saving_lines.length < (plan ? countLines(plan) : 0) && (
                  <span className="font-normal text-hit/80"> (on the {basket.saving_lines.length} that are sold online)</span>
                )}
              </p>
            )}
          </div>
          <div role="group" aria-label="Basket" className="flex rounded-xl border border-line bg-panel-2 p-1 text-sm">
            {(["with_swaps", "as_prescribed"] as const).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
                className={`rounded-lg px-3 py-1.5 font-medium transition ${mode === m ? "bg-hit text-bg" : "text-muted hover:text-ink"}`}
              >
                {m === "with_swaps" ? "Cheapest (same-salt swaps)" : "Exactly as prescribed"}
              </button>
            ))}
          </div>
        </div>
        <p className="flex items-center gap-1.5 border-t border-hit/20 px-6 py-2.5 text-xs text-faint">
          <Stethoscope className="h-3.5 w-3.5" />
          Swaps have the same salt, strength and form. Ask your doctor or pharmacist before switching brands.
        </p>
      </div>

      {/* One card per order */}
      {plan?.stores.map((s) => (
        <div key={s.platform} className="rise card p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Store className="h-4 w-4 text-hit" />
              <h3 className="font-semibold">{s.platform}</h3>
              <span className={`flex items-center gap-1 text-xs ${s.free_delivery ? "text-hit" : "text-miss"}`}>
                <Truck className="h-3 w-3" /> {s.free_delivery ? "free delivery" : `${inr(s.fee)} delivery`}
              </span>
            </div>
            <div className="tnum text-sm">
              <span className="text-muted">{inr(s.subtotal)}{s.fee > 0 && ` + ${inr(s.fee)}`} = </span>
              <span className="font-semibold">{inr(s.total)}</span>
            </div>
          </div>
          <div className="space-y-2">
            {s.lines.map((o) => {
              const href = buyLink(o);
              return (
                <div key={o.line} className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel-2 px-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{o.brand}</span>
                      {!o.prescribed && (
                        <span className="rounded bg-hit/15 px-1.5 py-0.5 text-[10px] font-semibold text-hit">
                          SWAP for {name(o.line)}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 line-clamp-1 text-xs text-faint" title={o.medicine_name}>
                      {o.manufacturer ? `${o.manufacturer} · ` : ""}
                      {o.packs} × {o.pack_estimated ? "~" : ""}
                      {o.pack_size} tablets
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="tnum font-mono text-sm font-semibold">{inr(o.item_cost)}</div>
                    <div className="tnum text-[11px] text-muted">{o.pack_estimated ? "~" : ""}{inr(o.per_tablet)}/tablet</div>
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
        </div>
      ))}

      {showSingle && alt && plan && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-panel-2 px-5 py-3 text-sm">
          <span className="flex items-center gap-2 text-muted">
            <ShoppingCart className="h-4 w-4" /> Prefer one order? <span className="text-ink">{alt.stores[0].platform}</span> has everything
          </span>
          <span className="tnum">
            {inr(alt.total)} <span className="text-muted">({alt.total > plan.total ? `+${inr(alt.total - plan.total)}` : "same"})</span>
          </span>
        </div>
      )}

      {basket.unavailable.length > 0 && (
        <div className="flex items-start gap-2 rounded-xl border border-miss/30 bg-miss/[0.07] px-4 py-3 text-sm text-miss">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          Not sold online for this PIN right now: {basket.unavailable.map(name).join(", ")}.
        </div>
      )}
      {mode === "as_prescribed" && plan && countLines(plan) < (basket.with_swaps.best ? countLines(basket.with_swaps.best) : 0) && (
        <p className="px-1 text-xs text-faint">
          Some prescribed brands aren&apos;t sold online here; the cheapest basket covers them with same-salt brands.
        </p>
      )}
      {running && <p className="px-1 text-xs text-faint">Still finishing: prices may update.</p>}
    </div>
  );
}

function countLines(plan: BasketPlan) {
  return plan.stores.reduce((n, s) => n + s.lines.length, 0);
}

function ChooseLine({ line, onPick }: { line: RxLine; onPick: (line: number, query: string) => void }) {
  if (!line.choose) return null;
  return (
    <div className="rise card p-4">
      <div className="text-sm">
        <span className="font-semibold">Which {line.query}?</span>{" "}
        <span className="text-muted">It comes in several strengths; pick the one on the prescription. The other medicines are already priced.</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {line.choose.options.slice(0, 6).map((o) => (
          <button
            key={o.query}
            type="button"
            onClick={() => onPick(line.line, o.query)}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-panel-2 px-3 py-1.5 text-sm hover:border-hit/50 hover:text-hit"
          >
            <PillIcon className="h-3.5 w-3.5 text-faint" /> {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
