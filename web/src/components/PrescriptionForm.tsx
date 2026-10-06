"use client";

import { Loader2, MapPin, Plus, Search, Stethoscope, X } from "lucide-react";
import type { RxItem } from "@/lib/api";
import { KITS, matchingKit } from "@/lib/kits";

export const RX_EXAMPLE: RxItem[] = [
  { q: "Dolo 650", tablets: 30 },
  { q: "Stamlo 5", tablets: null },
  { q: "Atorbest 10", tablets: null },
];

const MAX_LINES = 8;

/** "Dolo 650 x30", "Stamlo 5 - 60 tabs", "Pan 40" → {q, tablets}. */
export function parseLine(text: string): RxItem | null {
  const t = text.replace(/^[\s\-•*\d.)]+(?=[A-Za-z])/, "").trim();
  if (!t) return null;
  const m = t.match(/^(.*?)\s*(?:[x×*]\s*(\d{1,3})|[-–,]\s*(\d{1,3})\s*(?:tabs?|tablets?|caps?|capsules?)?)\s*$/i);
  if (m && m[1].trim()) return { q: m[1].trim(), tablets: Number(m[2] ?? m[3]) };
  return { q: t, tablets: null };
}

export default function PrescriptionForm({
  items,
  setItems,
  pincode,
  setPincode,
  running,
  onSubmit,
  colorKits = false,
}: {
  colorKits?: boolean;
  items: RxItem[];
  setItems: (items: RxItem[]) => void;
  pincode: string;
  setPincode: (p: string) => void;
  running: boolean;
  onSubmit: () => void;
}) {
  const update = (i: number, patch: Partial<RxItem>) => setItems(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const remove = (i: number) => setItems(items.length > 1 ? items.filter((_, j) => j !== i) : [{ q: "", tablets: null }]);
  const valid = items.filter((it) => it.q.trim().length >= 2);
  const kit = matchingKit(items);

  const onPaste = (i: number, e: React.ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\n")) return;
    e.preventDefault();
    const parsed = text.split(/\r?\n/).map(parseLine).filter((x): x is RxItem => x !== null);
    // A pasted list replaces this row and everything after it (never duplicates rows already there).
    const next = [...items.slice(0, i), ...parsed].filter((it) => it.q.trim()).slice(0, MAX_LINES);
    setItems(next.length ? next : [{ q: "", tablets: null }]);
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!running && valid.length && pincode.length === 6) onSubmit();
      }}
      className="card mt-6 space-y-2 p-3"
    >
      <div className="px-1 pb-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-faint">Common prescriptions</span>
          {KITS.map((k) => (
            <button
              key={k.id}
              type="button"
              onClick={() => setItems(k.items)}
              aria-pressed={kit?.id === k.id}
              className={`rounded-full border px-3 py-1 text-xs transition ${
                colorKits
                  ? `font-semibold ${kit?.id === k.id ? "border-accent bg-accent text-white" : "border-accent/40 bg-accent/5 text-accent hover:bg-accent/10"}`
                  : kit?.id === k.id
                    ? "border-hit/60 bg-hit/10 text-hit"
                    : "border-line text-muted hover:border-hit/40 hover:text-ink"
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>
        {kit && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-sem">
            <Stethoscope className="h-3.5 w-3.5 shrink-0" />
            Typical {kit.label.toLowerCase()} prescription: edit it to match yours. Ask your doctor before changing medicines.
          </p>
        )}
      </div>
      <div className="hidden grid-cols-[minmax(0,1fr)_7.5rem_2rem] gap-2 px-1 text-[11px] uppercase tracking-wider text-faint sm:grid">
        <span>Medicine (brand or salt with strength)</span>
        <span>Tablets (optional)</span>
        <span />
      </div>
      {items.map((it, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,1fr)_5.5rem_2rem] gap-2 sm:grid-cols-[minmax(0,1fr)_7.5rem_2rem]">
          <label className="sr-only" htmlFor={`rx-q-${i}`}>Medicine {i + 1}</label>
          <input
            id={`rx-q-${i}`}
            value={it.q}
            onChange={(e) => update(i, { q: e.target.value })}
            onPaste={(e) => onPaste(i, e)}
            placeholder={i === 0 ? "e.g. Dolo 650 (paste a whole list to fill every row)" : "Medicine"}
            className="w-full rounded-lg border border-line bg-bg px-3 py-2.5 text-sm outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-hit placeholder:text-faint focus:border-hit/50"
          />
          <label className="sr-only" htmlFor={`rx-t-${i}`}>Tablets for medicine {i + 1}</label>
          <input
            id={`rx-t-${i}`}
            value={it.tablets ?? ""}
            onChange={(e) => {
              const n = e.target.value.replace(/\D/g, "").slice(0, 3);
              update(i, { tablets: n ? Number(n) : null });
            }}
            inputMode="numeric"
            placeholder="1 pack"
            className="tnum w-full rounded-lg border border-line bg-bg px-3 py-2.5 font-mono text-sm outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-hit placeholder:text-faint focus:border-hit/50"
          />
          <button
            type="button"
            onClick={() => remove(i)}
            aria-label={`Remove medicine ${i + 1}`}
            className="grid place-items-center rounded-lg text-faint hover:bg-panel-2 hover:text-bad"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          disabled={items.length >= MAX_LINES}
          onClick={() => setItems([...items, { q: "", tablets: null }])}
          className="flex items-center gap-1.5 rounded-lg border border-dashed border-line px-3 py-2 text-sm text-muted hover:border-hit/40 hover:text-ink disabled:opacity-40"
        >
          <Plus className="h-4 w-4" /> Add medicine
        </button>
        <button
          type="button"
          onClick={() => setItems(RX_EXAMPLE)}
          className="rounded-lg px-3 py-2 text-xs text-muted hover:text-ink"
        >
          Try an example
        </button>
        <div className="relative ml-auto w-36">
          <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <label className="sr-only" htmlFor="rx-pin">Delivery PIN code</label>
          <input
            id="rx-pin"
            value={pincode}
            onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            placeholder="PIN"
            className="tnum w-full rounded-lg border border-line bg-bg py-2.5 pl-9 pr-3 font-mono text-sm outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-hit focus:border-hit/50"
          />
        </div>
        <button
          disabled={running || !valid.length || pincode.length !== 6}
          className="flex items-center justify-center gap-2 rounded-lg bg-hit px-5 py-2.5 text-sm font-semibold text-bg transition hover:brightness-110 disabled:opacity-40"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Find the cheapest basket
        </button>
      </div>
      <p className="px-1 text-[11px] text-faint">
        Up to {MAX_LINES} medicines. Leave the count empty to buy one pack (or one bottle/tube). Every medicine is searched at the same time.
      </p>
    </form>
  );
}
