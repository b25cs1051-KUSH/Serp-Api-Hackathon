"use client";

import { Pill as PillIcon } from "lucide-react";
import type { ChooseOptions } from "@/lib/api";

/** The search named a medicine without its strength ("paracetamol", "Dolo"). Nothing was searched yet. */
export default function ChooseCard({ choose, onPick }: { choose: ChooseOptions; onPick: (query: string) => void }) {
  return (
    <div className="rise card p-6">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sem">One more detail</div>
      <p className="mt-2 text-lg font-semibold">Which {choose.query} do you need?</p>
      <p className="mt-1 text-sm text-muted">
        {choose.reason === "several products share this name"
          ? "Several medicines are sold under this name. Pick the one on your prescription."
          : "It comes in more than one strength or form. Pick the one on your prescription."}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {choose.options.map((o) => (
          <button
            key={o.query}
            type="button"
            onClick={() => onPick(o.query)}
            className="flex items-center gap-2 rounded-lg border border-line bg-panel-2 px-3.5 py-2 text-sm text-ink transition hover:border-hit/50 hover:text-hit focus-visible:outline-2 focus-visible:outline-hit"
          >
            <PillIcon className="h-3.5 w-3.5 text-faint" />
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
