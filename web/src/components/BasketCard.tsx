"use client";

import { AlertTriangle, Pill as PillIcon } from "lucide-react";
import { type BasketResult, type RxItem, type RxLine } from "@/lib/api";
import LineComparison from "./LineComparison";
import { PLANS, PlanHeader, SwapNote } from "./PlanCards";
import StoreOrders from "./StoreOrders";

/** A whole prescription: each way to buy it followed by its own orders, then each medicine compared. */
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
  const skipped = Object.values(lines).filter((l) => l.status === "choose");
  const name = (i: number) => items[i]?.q ?? lines[i]?.query ?? `Medicine ${i + 1}`;

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

  const priced = items.length - skipped.length;

  return (
    <div className="space-y-4">
      {skipped.map((l) => <ChooseLine key={l.line} line={l} onPick={onPick} />)}

      {PLANS.map(({ id, pick }) => {
        const plan = pick(basket);
        return (
          <section key={id} className="space-y-3">
            <PlanHeader basket={basket} id={id} total={priced} />
            {plan && (
              <div className="border-l-2 border-line pl-3 md:pl-4">
                <StoreOrders plan={plan} items={items} />
              </div>
            )}
          </section>
        );
      })}
      <SwapNote basket={basket} />

      <LineComparison basket={basket} lines={lines} items={items} />

      {basket.unavailable.length > 0 && (
        <div className="flex items-start gap-2 rounded-xl border border-miss/30 bg-miss/[0.07] px-4 py-3 text-sm text-miss">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          Not sold online for this PIN right now: {basket.unavailable.map(name).join(", ")}.
        </div>
      )}
      {running && <p className="px-1 text-xs text-faint">Still finishing: prices may update.</p>}
    </div>
  );
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
