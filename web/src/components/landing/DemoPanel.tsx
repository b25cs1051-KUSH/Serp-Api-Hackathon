"use client";

import { Loader2, Play, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { API_URL, fmtMs, inr, type BasketResult, type Call } from "@/lib/api";
import { usePrescription } from "@/lib/usePrescription";
import { DEMO, recordedLabel } from "./demo";

const KIND = {
  exact: { label: "EXACT", cls: "bg-hit/15 text-hit" },
  semantic: { label: "SEMANTIC", cls: "bg-sem/15 text-sem" },
  api: { label: "API · 1 credit", cls: "bg-miss/15 text-miss" },
  passthrough: { label: "API · 1 credit", cls: "bg-miss/15 text-miss" },
} as const;

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Recorded calls appear at their real start time (all at once with reduced motion). */
function useReplay(calls: Call[], active: boolean) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!active) return;
    if (reducedMotion()) {
      const t = setTimeout(() => setShown(calls.length), 0);
      return () => clearTimeout(t);
    }
    const timers = calls.map((c, i) => setTimeout(() => setShown((n) => Math.max(n, i + 1)), 400 + c.start_ms));
    return () => timers.forEach(clearTimeout);
  }, [calls, active]);
  return shown;
}

type Waking = "idle" | "waking" | "failed";

/** 2. The split demo: the cheapest basket on the left, the SerpApi calls behind it on the right. */
export default function DemoPanel() {
  const rx = usePrescription();
  const [live, setLive] = useState(false);
  const [waking, setWaking] = useState<Waking>("idle");
  const cancel = useRef(false);
  const shown = useReplay(DEMO.calls, !live);

  useEffect(() => {
    cancel.current = false; // React may mount twice in development
    return () => {
      cancel.current = true;
    };
  }, []);

  // Free Render instances sleep after 15 min: poll /api/health (free) until it answers, then run once.
  const runLive = async () => {
    if (waking === "waking" || rx.state.status === "running") return;
    setWaking("waking");
    const deadline = Date.now() + 150_000;
    while (!cancel.current && Date.now() < deadline) {
      try {
        const r = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
        if (r.ok) {
          setWaking("idle");
          setLive(true);
          rx.run(DEMO.items, DEMO.pincode, false);
          return;
        }
      } catch {
        /* still asleep */
      }
      await new Promise((res) => setTimeout(res, 3000));
    }
    if (!cancel.current) setWaking("failed");
  };

  const calls = live ? rx.state.calls : DEMO.calls.slice(0, shown);
  const basket: BasketResult | null = live ? rx.state.basket : DEMO.basket;
  const running = live && rx.state.status === "running";
  const done = live ? rx.state.done : shown === DEMO.calls.length ? DEMO.summary : null;
  const spent = calls.filter((c) => c.credit).length;

  return (
    <section className="py-12" aria-labelledby="demo-title">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">A real prescription</div>
          <h2 id="demo-title" className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            Four medicines, the cheapest basket, and every lookup behind it
          </h2>
          <p className="mt-2 text-sm text-muted">
            {live
              ? `Live from the price engine, PIN ${DEMO.pincode}.`
              : `${recordedLabel(DEMO)}, PIN ${DEMO.pincode}. Every lookup came from the Redis cache.`}
          </p>
        </div>
        <button
          type="button"
          onClick={runLive}
          disabled={waking === "waking" || running}
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-panel px-4 py-2.5 text-sm font-medium hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
        >
          {waking === "waking" || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Run it live
        </button>
      </div>

      {waking === "waking" && (
        <p role="status" className="mb-4 rounded-lg border border-line bg-panel-2 px-4 py-3 text-sm text-muted">
          Waking up the price engine (about a minute on the free server)…
        </p>
      )}
      {waking === "failed" && (
        <p role="alert" className="mb-4 rounded-lg border border-bad/40 px-4 py-3 text-sm text-bad">
          The price engine didn&apos;t wake up. Try again in a minute; the recorded run above is real.
        </p>
      )}
      {live && rx.state.error && (
        <p role="alert" className="mb-4 rounded-lg border border-bad/40 px-4 py-3 text-sm text-bad">{rx.state.error}</p>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <BasketSide basket={basket} running={running} />
        <div className="theme-console min-w-0 rounded-xl p-4 sm:p-5">
          <div className="flex items-center justify-between text-xs text-muted">
            <span className="font-mono">SerpApi calls</span>
            {running && <span className="flex items-center gap-1.5 text-hit"><span className="pulse-dot h-1.5 w-1.5 rounded-full bg-hit" /> live</span>}
          </div>
          <ol tabIndex={0} aria-label="SerpApi calls" className="mt-3 max-h-[420px] space-y-1 overflow-y-auto pr-1 font-mono text-xs focus-visible:outline-2 focus-visible:outline-hit" aria-live="polite">
            {calls.map((c) => (
              <li key={c.n} className="rise flex items-start gap-2 rounded-md bg-panel-2 px-2.5 py-1.5">
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${KIND[c.kind].cls}`}>
                  {KIND[c.kind].label}
                  {c.kind === "semantic" && c.similarity != null ? ` ${c.similarity.toFixed(3)}` : ""}
                </span>
                <span className="min-w-0 flex-1 truncate text-ink" title={c.query}>{c.tag}</span>
                <span className="tnum shrink-0 text-muted">{fmtMs(c.ms)}</span>
              </li>
            ))}
            {calls.length === 0 && <li className="py-6 text-center text-muted">{running ? "waiting for the first lookup…" : "…"}</li>}
          </ol>
            {!live && shown === DEMO.calls.length && (
              <div className="rise mt-2 flex items-start gap-2 rounded-md border border-bad/30 bg-panel-2 px-2.5 py-1.5 font-mono text-xs">
                <span className="shrink-0 rounded bg-bad/15 px-1.5 py-0.5 text-[10px] font-semibold text-bad">
                  <ShieldAlert className="-mt-0.5 mr-0.5 inline h-3 w-3" />
                  DOSAGE GUARD
                </span>
                <span className="min-w-0 flex-1 text-ink">
                  &ldquo;{DEMO.dosage_guard.input}&rdquo; vs cached &ldquo;{DEMO.dosage_guard.nearest}&rdquo;: {DEMO.dosage_guard.similarity.toFixed(3)} similar, different dose, never reused
                </span>
              </div>
            )}
          <div className="tnum mt-3 border-t border-line pt-3 font-mono text-xs text-muted">
            {calls.length} lookups · <span className={spent ? "text-miss" : "text-hit"}>{spent} credit{spent === 1 ? "" : "s"} spent</span>
            {done && <> · {fmtMs(done.total_ms)}</>}
            {basket && <> · {basket.stats.combinations.toLocaleString("en-IN")} baskets compared in {fmtMs(basket.stats.ms)}</>}
          </div>
          {!live && <p className="mt-2 text-[11px] text-faint">The dosage-guard line is Cache Lab on the same cache, {DEMO.recorded_at}.</p>}
        </div>
      </div>
    </section>
  );
}

function BasketSide({ basket, running }: { basket: BasketResult | null; running: boolean }) {
  const best = basket?.with_swaps.best;
  const prescribed = basket?.as_prescribed.best;
  if (!best) {
    return (
      <div className="min-w-0 rounded-xl border border-line bg-panel p-5">
        <div className="h-5 w-40 rounded shimmer" />
        <div className="mt-4 h-24 rounded shimmer" />
        <p className="mt-3 text-sm text-muted">{running ? "Comparing brands and pharmacies…" : ""}</p>
      </div>
    );
  }
  return (
    <div className="min-w-0 rounded-xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm text-muted">Cheapest basket, delivered</span>
        <span className="tnum font-mono text-3xl font-semibold">{inr(best.total)}</span>
      </div>
      <p className="mt-1 text-sm text-muted">
        {best.stores.length} order{best.stores.length === 1 ? "" : "s"} · {best.fees_total === 0 ? "free delivery" : `${inr(best.fees_total)} delivery`}
        {prescribed && prescribed.total > best.total && (
          <> · <span className="font-medium text-hit">{inr(prescribed.total - best.total)} less</span> than {inr(prescribed.total)} as prescribed</>
        )}
      </p>
      <div className="mt-4 space-y-3">
        {best.stores.map((s) => (
          <div key={s.platform} className="rounded-lg border border-line">
            <div className="flex items-center justify-between border-b border-line px-3 py-2 text-sm">
              <span className="font-medium">{s.platform}</span>
              <span className="tnum font-mono text-xs text-muted">
                {inr(s.subtotal)} + {s.fee === 0 ? "free delivery" : `${inr(s.fee)} delivery`}
              </span>
            </div>
            <ul className="divide-y divide-line">
              {s.lines.map((o) => (
                <li key={o.line} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="min-w-0">
                    {o.brand}
                    {!o.prescribed && <span className="ml-1.5 rounded bg-hit/15 px-1.5 py-0.5 text-[10px] font-semibold text-hit">SWAP</span>}
                    <span className="block text-xs text-faint">
                      {o.unit === "item" ? `${o.packs} item${o.packs === 1 ? "" : "s"}` : `${o.packs} × ${o.pack_estimated ? "~" : ""}${o.pack_size} tablets`}
                    </span>
                  </span>
                  <span className="tnum shrink-0 font-mono">{inr(o.item_cost)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">Same salt, strength and form. Ask your doctor or pharmacist before switching brands.</p>
    </div>
  );
}
