"use client";

import { useState } from "react";
import Alternatives from "@/components/Alternatives";
import AnswerCard from "@/components/AnswerCard";
import BasketCard from "@/components/BasketCard";
import ChooseCard from "@/components/ChooseCard";
import PrescriptionForm, { RX_EXAMPLE } from "@/components/PrescriptionForm";
import Results from "@/components/Results";
import SearchBox, { ModeToggle, type Mode } from "@/components/shell/SearchBox";
import SiteFooter from "@/components/shell/SiteFooter";
import SiteHeader from "@/components/shell/SiteHeader";
import type { RxItem } from "@/lib/api";
import { usePrescription } from "@/lib/usePrescription";
import { useSearch } from "@/lib/useSearch";

const EXAMPLES = ["Stamlo 5", "Dolo 650", "Glyciphage SR 500", "Atorvastatin 10mg", "Pan-D"];

/** The shop: what a buyer sees. No calls, credits, timings or cache here. */
export default function ShopView() {
  const [query, setQuery] = useState("");
  const [pincode, setPincode] = useState("110001");
  const [mode, setMode] = useState<Mode>("one");
  const [rxItems, setRxItems] = useState<RxItem[]>(RX_EXAMPLE);

  // One-medicine searches resolve the top listings' product pages; prescriptions don't (as before the split).
  const { state, run } = useSearch();
  const running = state.status === "running";
  const rx = usePrescription();
  const rxRunning = rx.state.status === "running";

  const submit = (q = query) => {
    const text = q.trim();
    if (!text || running) return;
    setQuery(text);
    run(text, pincode, true);
  };
  const submitRx = (items = rxItems) => {
    const clean = items.map((it) => ({ q: it.q.trim().replace(/\s+/g, " "), tablets: it.tablets })).filter((it) => it.q.length >= 2);
    if (!clean.length || rxRunning) return;
    rx.run(clean, pincode, false);
  };
  const pickRx = (line: number, q: string) => {
    const items = rx.state.items.map((it, i) => (i === line ? { ...it, q } : it));
    setRxItems(items);
    rx.run(items, rx.state.pincode, false);
  };

  return (
    <main className="mx-auto w-full max-w-7xl px-4 pb-24 sm:px-6">
      <SiteHeader nav={false} tagline="Medicine prices, delivered" />

      <section className="pt-8 pb-8">
        <h1 className="max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
          The real price of your medicine, <span className="bg-gradient-to-r from-hit to-sem bg-clip-text text-transparent">delivered to your PIN</span>.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          Compare 1mg, PharmEasy, Apollo, Medplus and more with delivery to your PIN included, and see cheaper brands with the same salt.
        </p>

        <ModeToggle mode={mode} onChange={setMode} />

        {mode === "rx" && (
          <PrescriptionForm items={rxItems} setItems={setRxItems} pincode={pincode} setPincode={setPincode} running={rxRunning} onSubmit={() => submitRx()} />
        )}
        {mode === "one" && (
          <>
            <SearchBox query={query} setQuery={setQuery} pincode={pincode} setPincode={setPincode} running={running} onSubmit={() => submit()} />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-faint">try:</span>
              {EXAMPLES.map((e) => (
                <button key={e} onClick={() => submit(e)} disabled={running} className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-hit/40 hover:text-ink disabled:opacity-40">
                  {e}
                </button>
              ))}
            </div>
          </>
        )}
      </section>

      {mode === "rx" && rx.state.status !== "idle" && (
        <section className="space-y-5">
          {rx.state.error && <div className="card border-bad/40 p-4 text-sm text-bad">{rx.state.error}</div>}
          <BasketCard basket={rx.state.basket} lines={rx.state.lines} items={rx.state.items} running={rxRunning} onPick={pickRx} />
        </section>
      )}

      {mode === "one" && state.status !== "idle" && (
        <section className="space-y-5">
          {state.error && <div className="card border-bad/40 p-4 text-sm text-bad">{state.error}</div>}
          {state.choose ? (
            <ChooseCard choose={state.choose} onPick={submit} />
          ) : (
            <>
              {state.alternatives && state.alternatives.matched_by !== "exact" && (
                <p className="text-sm text-muted">
                  Showing results for <span className="font-medium text-ink">{state.alternatives.matched_brand ?? state.alternatives.composition.name}</span>{" "}
                  (you typed &ldquo;{state.query}&rdquo;).
                </p>
              )}
              {!(state.status === "error" && state.listings === null) && (
                <>
                  <AnswerCard query={state.query} listings={state.listings} alternatives={state.alternatives} running={running} />
                  <Results listings={state.listings} query={state.query} pincode={state.pincode} linksResolved={state.linksResolved} wantLinks={state.links} />
                </>
              )}
              <div id="alternatives" className="scroll-mt-4">
                <Alternatives result={state.alternatives} running={running} />
              </div>
            </>
          )}
        </section>
      )}

      <SiteFooter />
    </main>
  );
}
