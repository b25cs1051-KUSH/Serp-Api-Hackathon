"use client";

import { Check, Crown, ShoppingCart, Stethoscope } from "lucide-react";
import { inr, type BasketPlan, type BasketResult } from "@/lib/api";

export type PlanId = "cheapest" | "single" | "prescribed";

export const PLANS: { id: PlanId; title: string; sub: string; pick: (b: BasketResult) => BasketPlan | null }[] = [
  { id: "cheapest", title: "Cheapest overall", sub: "Same-salt swaps, from any pharmacies", pick: (b) => b.with_swaps.best },
  { id: "single", title: "One pharmacy", sub: "Same-salt swaps, everything in one order", pick: (b) => b.with_swaps.single_store },
  { id: "prescribed", title: "Exactly as prescribed", sub: "Your brands, at their cheapest pharmacies", pick: (b) => b.as_prescribed.best },
];

export const countLines = (plan: BasketPlan) => plan.stores.reduce((n, s) => n + s.lines.length, 0);

/** The three ways to buy the prescription, side by side. */
export default function PlanCards({
  basket,
  total,
  selected,
  onSelect,
}: {
  basket: BasketResult;
  total: number;
  selected: PlanId;
  onSelect: (id: PlanId) => void;
}) {
  const best = basket.with_swaps.best;
  return (
    <div className="space-y-2">
      <div className="grid gap-3 md:grid-cols-3">
        {PLANS.map(({ id, title, sub, pick }) => {
          const plan = pick(basket);
          const active = selected === id;
          const extra = plan && best && id !== "cheapest" ? plan.total - best.total : 0;
          return (
            <div
              key={id}
              className={`rise flex flex-col rounded-2xl border p-5 transition ${
                active ? "border-hit/60 bg-hit/[0.07] ring-1 ring-hit/30" : "border-line bg-panel"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className={`text-[11px] font-semibold uppercase tracking-[0.12em] ${id === "cheapest" ? "text-hit" : "text-muted"}`}>{title}</div>
                  <div className="mt-0.5 text-xs text-faint">{sub}</div>
                </div>
                {id === "cheapest" && plan && (
                  <span className="flex shrink-0 items-center gap-1 rounded-full bg-hit/15 px-2 py-0.5 text-[10px] font-semibold text-hit">
                    <Crown className="h-3 w-3" /> Best value
                  </span>
                )}
              </div>

              {plan ? (
                <>
                  <div className="mt-3 text-3xl font-semibold tracking-tight">
                    <span className="tnum">{inr(plan.total)}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted">
                    {plan.stores.length === 1 ? `1 order: ${plan.stores[0].platform}` : `${plan.stores.length} orders: ${plan.stores.map((s) => s.platform).join(" + ")}`}
                  </p>
                  <p className="text-sm text-muted">
                    {plan.fees_total === 0 ? "Free delivery" : `${inr(plan.fees_total)} delivery`}
                    {countLines(plan) < total && ` · ${countLines(plan)} of ${total} medicines`}
                  </p>
                  {extra > 0.005 && <p className="mt-1 text-xs text-miss">+{inr(extra)} vs the cheapest plan</p>}
                </>
              ) : (
                <p className="mt-3 text-sm text-muted">
                  {id === "single" ? "No single pharmacy sells every medicine here." : "None of the prescribed brands is sold online here."}
                </p>
              )}

              <div className="flex-1" />
              <button
                type="button"
                disabled={!plan}
                aria-pressed={active}
                onClick={() => onSelect(id)}
                className={`mt-4 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition disabled:opacity-40 ${
                  active ? "bg-hit text-bg" : "border border-line text-ink hover:border-hit/50"
                }`}
              >
                {active ? <Check className="h-4 w-4" /> : <ShoppingCart className="h-4 w-4" />}
                {active ? "Selected" : "Choose this plan"}
              </button>
            </div>
          );
        })}
      </div>
      <p className="flex items-center gap-1.5 px-1 text-xs text-faint">
        <Stethoscope className="h-3.5 w-3.5" />
        Swaps have the same salt, strength and form. Ask your doctor or pharmacist before switching brands.
        {basket.saving != null && basket.saving > 0 && (
          <span className="text-hit"> Swaps save {inr(basket.saving)} on the prescribed brands sold online.</span>
        )}
      </p>
    </div>
  );
}
