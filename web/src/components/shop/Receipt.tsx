"use client";

import BasketCard from "@/components/BasketCard";
import { inr } from "@/lib/api";
import type { PrescriptionState } from "@/lib/usePrescription";
import { ErrorNote } from "./ShopStates";

/**
 * The prescription result: the saving over the prescribed brands, then each plan (cheapest overall,
 * one pharmacy, exactly as prescribed) followed by its orders, then each medicine compared.
 */
export default function Receipt({ rx, onPick }: { rx: PrescriptionState; onPick: (line: number, q: string) => void }) {
  const best = rx.basket?.with_swaps.best;
  const prescribed = rx.basket?.as_prescribed.best;
  const less = best && prescribed ? prescribed.total - best.total : 0;

  return (
    <section className="space-y-5" aria-labelledby="receipt-title">
      <div>
        <h2 id="receipt-title" className="text-2xl font-semibold tracking-tight">Your cheapest basket</h2>
        <p className="mt-1 text-sm text-muted">
          {rx.items.length} medicine{rx.items.length === 1 ? "" : "s"}, delivered to {rx.pincode}
          {rx.status === "running" && " · comparing pharmacies…"}
        </p>
      </div>

      {rx.error && <ErrorNote message={rx.error} />}

      {best && less > 0.005 && (
        <p className="rounded-xl border border-hit/30 bg-hit/[0.07] px-4 py-3 text-sm">
          <span className="tnum font-mono text-lg font-semibold text-hit">{inr(less)} less</span>{" "}
          <span className="text-ink">than buying exactly as prescribed ({inr(prescribed!.total)}).</span>{" "}
          <span className="text-muted">Swaps have the same salt, strength and form. Ask your doctor or pharmacist before switching brands.</span>
        </p>
      )}

      <BasketCard basket={rx.basket} lines={rx.lines} items={rx.items} running={rx.status === "running"} onPick={onPick} />
    </section>
  );
}
