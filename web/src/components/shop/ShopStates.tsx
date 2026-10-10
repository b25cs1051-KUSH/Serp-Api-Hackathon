"use client";

import { AlertTriangle, ClipboardList, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

export function EmptyState({ onPaste }: { onPaste: () => void }) {
  return (
    <section className="pb-6 pt-2">
      <h1 className="max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">Lowest delivered price for your medicines.</h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
        Enter a medicine name below and set your 6-digit delivery PIN above, then select Search.
        Compare prices including delivery across pharmacies, alongside alternatives with the same salt, strength and form.
      </p>
      <button
        type="button"
        onClick={onPaste}
        className="mt-4 flex items-center gap-1.5 rounded-full border border-dashed border-accent/50 px-3 py-1.5 text-sm font-medium text-accent hover:bg-panel focus-visible:outline-2 focus-visible:outline-accent"
      >
        <ClipboardList className="h-4 w-4" /> Have a prescription? Paste it
      </button>
    </section>
  );
}

export function LoadingCards({ waking = false }: { waking?: boolean }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Finding prices">
      {waking && <p role="status" className="text-sm text-muted">Getting ready to compare prices…</p>}
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
    return <Note tone="warn">Today&apos;s search allowance is used up. Fully cached comparisons can still work; new lookups resume at 5:30 AM IST.</Note>;
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
