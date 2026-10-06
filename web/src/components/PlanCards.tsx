"use client";

import { ClipboardCheck, Crown, Stethoscope, Store, TrendingDown } from "lucide-react";
import { inr, type BasketPlan, type BasketResult } from "@/lib/api";

export type PlanId = "cheapest" | "single" | "prescribed";

export const PLANS: { id: PlanId; title: string; sub: string; pick: (b: BasketResult) => BasketPlan | null }[] = [
  { id: "cheapest", title: "Cheapest overall", sub: "Same-salt swaps, from any pharmacies", pick: (b) => b.with_swaps.best },
  { id: "single", title: "One pharmacy", sub: "Same-salt swaps, everything in one order", pick: (b) => b.with_swaps.single_store },
  { id: "prescribed", title: "Exactly as prescribed", sub: "Your brands, at their cheapest pharmacies", pick: (b) => b.as_prescribed.best },
];

export const countLines = (plan: BasketPlan) => plan.stores.reduce((n, s) => n + s.lines.length, 0);

/** One way to buy the prescription: its total, orders and delivery, above the orders themselves. */
/** Shop styling per plan: accent colour, tinted panel, icon. */
const SHOP_STYLE: Record<PlanId, { panel: string; title: string; icon: typeof Store }> = {
  cheapest: { panel: "border-hit/60 bg-hit/[0.08] border-l-[6px] border-l-hit", title: "text-hit", icon: TrendingDown },
  single: { panel: "border-sem/40 bg-sem/[0.06] border-l-[6px] border-l-sem", title: "text-sem", icon: Store },
  prescribed: { panel: "border-[#f59e0b]/50 bg-[#fef3c7]/60 border-l-[6px] border-l-[#d97706]", title: "text-[#92400e]", icon: ClipboardCheck },
};

export function PlanHeader({ basket, id, total, variant = "engine" }: { basket: BasketResult; id: PlanId; total: number; variant?: "engine" | "shop" }) {
  if (variant === "shop") return <ShopPlanHeader basket={basket} id={id} total={total} />;
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

function ShopPlanHeader({ basket, id, total }: { basket: BasketResult; id: PlanId; total: number }) {
  const { title, sub, pick } = PLANS.find((p) => p.id === id) ?? PLANS[0];
  const plan = pick(basket);
  const best = basket.with_swaps.best;
  const extra = plan && best && id !== "cheapest" ? plan.total - best.total : 0;
  const style = SHOP_STYLE[id];
  const Icon = style.icon;
  return (
    <div className={`rise flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-5 shadow-sm ${style.panel}`}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Icon aria-hidden className={`h-6 w-6 ${style.title}`} />
          <h3 className={`text-xl font-extrabold tracking-tight sm:text-2xl ${style.title}`}>{title}</h3>
          {id === "cheapest" && plan && (
            <span className="flex items-center gap-1 rounded-full bg-hit px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-white">
              <Crown className="h-3 w-3" /> Best value
            </span>
          )}
        </div>
        <div className="mt-0.5 text-sm text-muted">{sub}</div>
        {plan ? (
          <p className="mt-2 text-sm font-medium text-ink">
            {plan.stores.length === 1 ? `1 order: ${plan.stores[0].platform}` : `${plan.stores.length} orders: ${plan.stores.map((s) => s.platform).join(" + ")}`}
            {" · "}
            {plan.fees_total === 0 ? <span className="text-hit">free delivery</span> : <span className="text-miss">{inr(plan.fees_total)} delivery</span>}
            {countLines(plan) < total && <span className="text-bad"> · {countLines(plan)} of {total} medicines</span>}
          </p>
        ) : (
          <p className="mt-2 text-sm text-bad">
            {id === "single" ? "No single pharmacy sells every medicine here." : "None of the prescribed brands is sold online here."}
          </p>
        )}
      </div>
      {plan && (
        <div className="text-right">
          <div className={`tnum font-mono text-3xl font-bold tracking-tight ${id === "cheapest" ? "text-hit" : "text-ink"}`}>{inr(plan.total)}</div>
          {extra > 0.005 && <p className="text-sm font-semibold text-bad">+{inr(extra)} more</p>}
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
