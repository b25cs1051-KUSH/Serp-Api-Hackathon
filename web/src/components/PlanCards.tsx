"use client";

import { Crown, Stethoscope } from "lucide-react";
import { inr, type BasketPlan, type BasketResult } from "@/lib/api";

export type PlanId = "cheapest" | "single" | "prescribed";

export const PLANS: { id: PlanId; title: string; sub: string; pick: (b: BasketResult) => BasketPlan | null }[] = [
  { id: "cheapest", title: "Cheapest overall", sub: "Same-salt swaps, from any pharmacies", pick: (b) => b.with_swaps.best },
  { id: "single", title: "One pharmacy", sub: "Same-salt swaps, everything in one order", pick: (b) => b.with_swaps.single_store },
  { id: "prescribed", title: "Exactly as prescribed", sub: "Your brands, at their cheapest pharmacies", pick: (b) => b.as_prescribed.best },
];

export const countLines = (plan: BasketPlan) => plan.stores.reduce((n, s) => n + s.lines.length, 0);

/** One way to buy the prescription: its total, orders and delivery, above the orders themselves. */
export function PlanHeader({ basket, id, total }: { basket: BasketResult; id: PlanId; total: number }) {
  const { title, sub, pick } = PLANS.find((p) => p.id === id) ?? PLANS[0];
  const plan = pick(basket);
  const best = basket.with_swaps.best;
  const extra = plan && best && id !== "cheapest" ? plan.total - best.total : 0;
  const cheapest = id === "cheapest";
  return (
    <div className={`rise flex flex-wrap items-end justify-between gap-3 rounded-2xl border p-5 ${cheapest ? "border-hit/60 bg-hit/[0.07]" : "border-line bg-panel"}`}>
      <div>
        <div className="flex items-center gap-2">
          <span className={`text-[11px] font-semibold uppercase tracking-[0.12em] ${cheapest ? "text-hit" : "text-muted"}`}>{title}</span>
          {cheapest && plan && (
            <span className="flex items-center gap-1 rounded-full bg-hit/15 px-2 py-0.5 text-[10px] font-semibold text-hit">
              <Crown className="h-3 w-3" /> Best value
            </span>
          )}
        </div>
        <div className="mt-0.5 text-xs text-faint">{sub}</div>
        {plan ? (
          <p className="mt-2 text-sm text-muted">
            {plan.stores.length === 1 ? `1 order: ${plan.stores[0].platform}` : `${plan.stores.length} orders: ${plan.stores.map((s) => s.platform).join(" + ")}`}
            {" · "}
            {plan.fees_total === 0 ? "free delivery" : `${inr(plan.fees_total)} delivery`}
            {countLines(plan) < total && ` · ${countLines(plan)} of ${total} medicines`}
          </p>
        ) : (
          <p className="mt-2 text-sm text-muted">
            {id === "single" ? "No single pharmacy sells every medicine here." : "None of the prescribed brands is sold online here."}
          </p>
        )}
      </div>
      {plan && (
        <div className="text-right">
          <div className="tnum text-3xl font-semibold tracking-tight">{inr(plan.total)}</div>
          {extra > 0.005 && <p className="text-xs text-miss">+{inr(extra)} vs the cheapest plan</p>}
        </div>
      )}
    </div>
  );
}

export function SwapNote({ basket }: { basket: BasketResult }) {
  return (
    <p className="flex items-center gap-1.5 px-1 text-xs text-faint">
      <Stethoscope className="h-3.5 w-3.5" />
      Swaps have the same salt, strength and form. Ask your doctor or pharmacist before switching brands.
      {basket.saving != null && basket.saving > 0 && (
        <span className="text-hit"> Swaps save {inr(basket.saving)} on the prescribed brands sold online.</span>
      )}
    </p>
  );
}
