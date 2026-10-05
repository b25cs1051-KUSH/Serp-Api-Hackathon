"use client";

import { AlertTriangle, ClipboardList, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

export type Filter = "cheapest" | "free" | "swaps" | "fastest";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "cheapest", label: "Cheapest delivered" },
  { id: "free", label: "Free delivery" },
  { id: "swaps", label: "Same-salt swaps" },
  { id: "fastest", label: "Fastest delivery" },
];

export function FilterChips({ value, onChange }: { value: Filter; onChange: (f: Filter) => void }) {
  return (
    <div role="group" aria-label="Show" className="flex flex-wrap gap-2">
      {FILTERS.map((f) => (
        <button
          key={f.id}
          type="button"
          aria-pressed={value === f.id}
          onClick={() => onChange(f.id)}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium focus-visible:outline-2 focus-visible:outline-accent ${
            value === f.id ? "border-accent bg-accent text-white" : "border-line bg-panel text-muted hover:text-ink"
          }`}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}

/** Hours until delivery, from labels like "10-30 Mins / 1 Day", "Same Day / Store Pickup", "1-2 Days". */
export function deliveryHours(days?: string): number {
  if (!days) return 1e6;
  const mins = days.match(/(\d+)(?:\s*-\s*\d+)?\s*min/i);
  if (mins) return Number(mins[1]) / 60;
  if (/same day/i.test(days)) return 8;
  const d = days.match(/(\d+)(?:\s*-\s*\d+)?\s*day/i);
  return d ? Number(d[1]) * 24 : 1e6;
}

export function EmptyState({ examples, onSearch, onPaste }: { examples: string[]; onSearch: (q: string) => void; onPaste: () => void }) {
  return (
    <section className="py-10">
      <h1 className="max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">The lowest price for your medicines, delivered to your PIN.</h1>
      <p className="mt-2 max-w-xl text-sm text-muted">Search one medicine, or put your whole prescription in the cart and we&apos;ll find the cheapest way to buy it.</p>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        {examples.map((e) => (
          <button
            key={e}
            type="button"
            onClick={() => onSearch(e)}
            className="rounded-full border border-line bg-panel px-3 py-1.5 text-sm hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-accent"
          >
            {e}
          </button>
        ))}
        <button
          type="button"
          onClick={onPaste}
          className="flex items-center gap-1.5 rounded-full border border-dashed border-line px-3 py-1.5 text-sm text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
        >
          <ClipboardList className="h-4 w-4" /> Paste your prescription
        </button>
      </div>
    </section>
  );
}

export function LoadingCards() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Finding prices">
      <div className="h-44 rounded-xl shimmer" />
      <div className="h-24 rounded-xl shimmer" />
      <div className="h-24 rounded-xl shimmer" />
    </div>
  );
}

const ASLEEP = /can't reach the api|not healthy/i;

/**
 * The API's error in plain words. "Budget used up" gets its own message. When the API can't be
 * reached (the free server sleeps), polls /api/health (free) and says when it's back: searching
 * again is left to the user, so nothing re-runs (and spends credits) on its own.
 */
export function ErrorNote({ message }: { message: string }) {
  const asleep = ASLEEP.test(message);
  const [awake, setAwake] = useState(false);
  useEffect(() => {
    if (!asleep) return;
    let stop = false;
    const poll = () =>
      fetch(`${API_URL}/api/health`, { cache: "no-store" })
        .then((r) => (r.ok ? !stop && setAwake(true) : Promise.reject()))
        .catch(() => !stop && setTimeout(poll, 3000));
    poll();
    return () => {
      stop = true;
    };
  }, [asleep]);

  if (/budget/i.test(message)) {
    return <Note tone="warn">Today&apos;s demo search budget is used up. Medicines already searched today still work.</Note>;
  }
  if (asleep) {
    return awake ? (
      <Note tone="ok">The price engine is awake. Search again.</Note>
    ) : (
      <Note tone="warn" spin>
        Waking up the price engine (about a minute on the free server)…
      </Note>
    );
  }
  return <Note tone="bad">{message}</Note>;
}

function Note({ tone, spin, children }: { tone: "ok" | "warn" | "bad"; spin?: boolean; children: React.ReactNode }) {
  const cls = tone === "ok" ? "border-hit/40 text-hit" : tone === "warn" ? "border-miss/40 text-miss" : "border-bad/40 text-bad";
  return (
    <p role={tone === "bad" ? "alert" : "status"} className={`flex items-start gap-2 rounded-xl border bg-panel px-4 py-3 text-sm ${cls}`}>
      {spin ? <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
      <span>{children}</span>
    </p>
  );
}
