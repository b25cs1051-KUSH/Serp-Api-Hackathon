"use client";

import { Check, Plus } from "lucide-react";
import { useState } from "react";

/** A tablet count (empty = one pack) and "Add to cart". Shows "In cart" once added; adding again updates the count. */
export default function AddToCart({ name, inCart, onAdd, id }: { name: string; inCart: boolean; onAdd: (tablets: number | null) => void; id: string }) {
  const [tablets, setTablets] = useState("");
  return (
    <div className="flex items-center gap-2">
      <label className="sr-only" htmlFor={id}>Tablets of {name}</label>
      <input
        id={id}
        value={tablets}
        onChange={(e) => setTablets(e.target.value.replace(/\D/g, "").slice(0, 3))}
        inputMode="numeric"
        placeholder="1 pack"
        className="tnum w-20 rounded-lg border border-line bg-panel px-2.5 py-2 font-mono text-sm outline-none placeholder:text-faint focus:border-accent"
      />
      <button
        type="button"
        onClick={() => onAdd(tablets ? Number(tablets) : null)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-accent ${
          inCart ? "border-hit/40 bg-hit/10 text-hit" : "border-line bg-panel hover:border-accent/50"
        }`}
      >
        {inCart ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
        {inCart ? "In cart" : "Add to cart"}
      </button>
    </div>
  );
}
