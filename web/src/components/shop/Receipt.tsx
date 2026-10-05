"use client";

import { ArrowLeft, ShoppingCart } from "lucide-react";
import BasketCard from "@/components/BasketCard";
import { inr } from "@/lib/api";
import type { PrescriptionState } from "@/lib/usePrescription";
import { ErrorNote } from "./ShopStates";

/**
 * The receipt for the cart: the saving over the prescribed brands, then each plan (cheapest overall,
 * one pharmacy, exactly as prescribed) followed by its orders, then each medicine compared.
 */
export default function Receipt({
  rx,
  onPick,
  onEdit,
  onBack,
}: {
  rx: PrescriptionState;
  onPick: (line: number, q: string) => void;
  onEdit: () => void;
  onBack?: () => void;
}) {
  const best = rx.basket?.with_swaps.best;
  const prescribed = rx.basket?.as_prescribed.best;
  const less = best && prescribed ? prescribed.total - best.total : 0;
  const running = rx.status === "running";

  return (
    <section className="space-y-5 py-6" aria-labelledby="receipt-title">
      {onBack && (
        <button type="button" onClick={onBack} className="flex items-center gap-1.5 text-sm text-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Back to search
        </button>
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="receipt-title" className="text-2xl font-semibold tracking-tight">Your cheapest basket</h1>
          <p className="mt-1 text-sm text-muted">
            {rx.items.length} medicine{rx.items.length === 1 ? "" : "s"}, delivered to {rx.pincode}
            {running && " · comparing pharmacies…"}
          </p>
        </div>
        <button
          type="button"
          onClick={onEdit}
          className="flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-2 text-sm font-medium hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-accent"
        >
          <ShoppingCart className="h-4 w-4" /> Edit cart
        </button>
      </div>

      {rx.error && <ErrorNote message={rx.error} />}

      {best && less > 0.005 && (
        <p className="rounded-xl border border-hit/30 bg-hit/[0.07] px-4 py-3 text-sm">
          <span className="tnum font-mono text-lg font-semibold text-hit">{inr(less)} less</span>{" "}
          <span className="text-ink">than buying exactly as prescribed ({inr(prescribed!.total)}).</span>{" "}
          <span className="text-muted">Swaps have the same salt, strength and form. Ask your doctor or pharmacist before switching brands.</span>
        </p>
      )}

      <BasketCard basket={rx.basket} lines={rx.lines} items={rx.items} running={running} onPick={onPick} />
    </section>
  );
}
