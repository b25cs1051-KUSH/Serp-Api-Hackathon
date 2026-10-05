"use client";

import { ClipboardList, Loader2, MapPin, Pill as PillIcon, Search } from "lucide-react";

export type Mode = "one" | "rx";

/** "One medicine" / "Whole prescription". */
export function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div role="group" aria-label="What to search" className="mt-6 inline-flex rounded-xl border border-line bg-panel-2 p-1 text-sm">
      {([
        ["one", "One medicine", PillIcon],
        ["rx", "Whole prescription", ClipboardList],
      ] as const).map(([id, label, Icon]) => (
        <button
          key={id}
          type="button"
          aria-pressed={mode === id}
          onClick={() => onChange(id)}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${mode === id ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}
        >
          <Icon className="h-4 w-4" /> {label}
        </button>
      ))}
    </div>
  );
}

/** 6-digit PIN code input: keeps digits only. */
export function PinInput({ value, onChange, id = "pin", className = "" }: { value: string; onChange: (v: string) => void; id?: string; className?: string }) {
  return (
    <div className={`relative ${className}`}>
      <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
      <label className="sr-only" htmlFor={id}>Delivery PIN code</label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode="numeric"
        placeholder="PIN"
        className="tnum w-full rounded-lg border border-line bg-bg py-3 pl-9 pr-3 font-mono text-sm outline-none focus:border-hit/50"
      />
    </div>
  );
}

/** One-medicine search: name, PIN and Compare. */
export default function SearchBox({
  query,
  setQuery,
  pincode,
  setPincode,
  running,
  onSubmit,
}: {
  query: string;
  setQuery: (q: string) => void;
  pincode: string;
  setPincode: (p: string) => void;
  running: boolean;
  onSubmit: () => void;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="card mt-3 flex flex-col gap-2 p-2 md:flex-row"
    >
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
        <label className="sr-only" htmlFor="q">Medicine name</label>
        <input
          id="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Medicine name, e.g. Dolo 650"
          className="w-full rounded-lg bg-transparent py-3 pl-10 pr-3 text-base outline-none placeholder:text-faint"
        />
      </div>
      <PinInput value={pincode} onChange={setPincode} className="md:w-36" />
      <button
        disabled={running || !query.trim() || pincode.length !== 6}
        className="flex items-center justify-center gap-2 rounded-lg bg-hit px-6 py-3 text-sm font-semibold text-bg transition hover:brightness-110 disabled:opacity-40"
      >
        {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        Compare
      </button>
    </form>
  );
}
