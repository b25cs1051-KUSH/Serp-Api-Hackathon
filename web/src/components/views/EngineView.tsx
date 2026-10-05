"use client";

import { Coins, Link2, Repeat } from "lucide-react";
import { useEffect, useState } from "react";
import Alternatives from "@/components/Alternatives";
import BasketCard from "@/components/BasketCard";
import CacheExplorer from "@/components/CacheExplorer";
import CacheFlow from "@/components/CacheFlow";
import CacheLab from "@/components/CacheLab";
import ChooseCard from "@/components/ChooseCard";
import PrescriptionForm, { RX_EXAMPLE, parseLine } from "@/components/PrescriptionForm";
import Results from "@/components/Results";
import SearchBox, { ModeToggle, type Mode } from "@/components/shell/SearchBox";
import SiteFooter from "@/components/shell/SiteFooter";
import SiteHeader from "@/components/shell/SiteHeader";
import StatusPills from "@/components/shell/StatusPills";
import { SectionTitle, Stat } from "@/components/ui";
import UnderTheHood from "@/components/UnderTheHood";
import { fmtMs, type RxItem } from "@/lib/api";
import { useApiStatus } from "@/lib/useApiStatus";
import { asSearchState, usePrescription } from "@/lib/usePrescription";
import { useSearch } from "@/lib/useSearch";

const EXAMPLES = ["Stamlo 5", "Dolo 650", "Glyciphage SR 500", "Atorvastatin 10mg", "Pan-D"];

/** Under the hood: the same searches with every SerpApi call, cache decision and credit shown. */
export default function EngineView() {
  const { health, healthErr, account, stats, entries, refresh } = useApiStatus();

  const [query, setQuery] = useState("");
  const [pincode, setPincode] = useState("110001");
  const [links, setLinks] = useState(true);
  const [mode, setMode] = useState<Mode>("one");
  const [rxItems, setRxItems] = useState<RxItem[]>(RX_EXAMPLE);

  const { state, run } = useSearch(refresh);
  const running = state.status === "running";
  const rx = usePrescription(refresh);
  const rxRunning = rx.state.status === "running";

  const submit = (q = query) => {
    const text = q.trim();
    if (!text || running) return;
    setQuery(text);
    run(text, pincode, links);
  };
  const submitRx = (items = rxItems) => {
    const clean = items.map((it) => ({ q: it.q.trim().replace(/\s+/g, " "), tablets: it.tablets })).filter((it) => it.q.length >= 2);
    if (!clean.length || rxRunning) return;
    rx.run(clean, pincode, links);
  };
  const runRx = (items: RxItem[], pin: string) => rx.run(items, pin, false);
  const pickRx = (line: number, q: string) => {
    const items = rx.state.items.map((it, i) => (i === line ? { ...it, q } : it));
    setRxItems(items);
    rx.run(items, rx.state.pincode, links);
  };

  // Deep links: /engine?q=Dolo%20650&pin=110001 runs one medicine, /engine?rx=<lines, one per medicine>&pin=… a
  // prescription. Read once on load; started with product links off, so opening a link never pays for product pages.
  // The timer is cleared on unmount, so React's development double-mount starts the run once.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pin = /^[1-9]\d{5}$/.test(params.get("pin") ?? "") ? params.get("pin")! : "110001";
    const q = params.get("q")?.trim();
    const rx = (params.get("rx") ?? "")
      .split(/\r?\n|;/)
      .map(parseLine)
      .filter((x): x is RxItem => x !== null)
      .slice(0, 8);
    if (!q && !rx.length) return;
    const t = setTimeout(() => {
      setPincode(pin);
      setLinks(false);
      if (rx.length) {
        setMode("rx");
        setRxItems(rx);
        runRx(rx, pin);
      } else if (q) {
        setQuery(q);
        run(q, pin, false);
      }
    }, 0);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const s = stats?.session;

  return (
    <main className="mx-auto w-full max-w-7xl px-4 pb-24 sm:px-6">
      <SiteHeader tagline="SerpApi · Redis semantic cache · Gemini" />
      <StatusPills health={health} healthErr={healthErr} account={account} />

      <section className="pt-8 pb-8">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">Under the hood</div>
        <h1 className="mt-2 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">Every SerpApi call, cache decision and credit, live.</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          Run a medicine or a whole prescription and watch each lookup: an exact Redis hit, a semantic hit with its similarity score, or a
          SerpApi call that costs one credit. Run it again and it costs nothing. Below: how the cache decides, a lab to test it for free, and
          what is in Redis right now.
        </p>

        <ModeToggle mode={mode} onChange={setMode} />

        {mode === "rx" && (
          <PrescriptionForm items={rxItems} setItems={setRxItems} pincode={pincode} setPincode={setPincode} running={rxRunning} onSubmit={() => submitRx()} />
        )}
        {mode === "one" && <SearchBox query={query} setQuery={setQuery} pincode={pincode} setPincode={setPincode} running={running} onSubmit={() => submit()} />}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {mode === "one" && <span className="text-[11px] text-faint">try:</span>}
          {mode === "one" &&
            EXAMPLES.map((e) => (
              <button key={e} onClick={() => submit(e)} disabled={running} className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-hit/40 hover:text-ink disabled:opacity-40">
                {e}
              </button>
            ))}
          <label
            className="ml-auto flex cursor-pointer items-center gap-2 text-xs text-muted"
            title="Resolves each top listing's own pharmacy product page: 1 SerpApi call per link the first time, then cached."
          >
            <input type="checkbox" checked={links} onChange={(e) => setLinks(e.target.checked)} className="accent-[#34d399]" />
            <Link2 className="h-3.5 w-3.5" /> resolve direct pharmacy links
          </label>
        </div>
      </section>

      {mode === "rx" && rx.state.status !== "idle" && (
        <section className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-5">
            {rx.state.error && <div className="card border-bad/40 p-4 text-sm text-bad">{rx.state.error}</div>}
            <BasketCard basket={rx.state.basket} lines={rx.state.lines} items={rx.state.items} running={rxRunning} onPick={pickRx} />
          </div>
          <div className="min-w-0 space-y-3 lg:sticky lg:top-4 lg:self-start">
            <UnderTheHood
              state={asSearchState(rx.state)}
              note={
                rx.state.basket
                  ? `Basket optimiser: ${rx.state.basket.stats.combinations.toLocaleString("en-IN")} ways to buy it priced with each pharmacy's delivery rules in ${fmtMs(rx.state.basket.stats.ms)}`
                  : undefined
              }
            />
            {rx.state.status === "done" && (
              <button
                onClick={() => rx.run(rx.state.items, rx.state.pincode, links)}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-hit/30 bg-hit/10 py-3 text-sm font-medium text-hit hover:bg-hit/15"
              >
                <Repeat className="h-4 w-4" /> Run the same prescription again: watch it cost 0 credits
              </button>
            )}
          </div>
        </section>
      )}

      {mode === "one" && state.status !== "idle" && (
        <section className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-5">
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
                  <Results listings={state.listings} query={state.query} pincode={state.pincode} linksResolved={state.linksResolved} wantLinks={state.links} />
                )}
                <Alternatives result={state.alternatives} running={running} />
              </>
            )}
          </div>
          <div className="min-w-0 space-y-3 lg:sticky lg:top-4 lg:self-start">
            <UnderTheHood state={state} />
            {state.status === "done" && (
              <button
                onClick={() => run(state.query, state.pincode, state.links)}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-hit/30 bg-hit/10 py-3 text-sm font-medium text-hit hover:bg-hit/15"
              >
                <Repeat className="h-4 w-4" /> Run the same search again: watch it cost 0 credits
              </button>
            )}
          </div>
        </section>
      )}

      <section className="mt-16">
        <SectionTitle
          eyebrow="The cache"
          title="How a query decides whether to spend a credit"
          sub="Every SerpApi request goes through serpapi_cache: a drop-in replacement for serpapi.Client.search(). Similar questions reuse answers; different doses never do."
        />
        <CacheFlow threshold={health?.similarity_threshold} />
      </section>

      <section className="mt-16">
        <SectionTitle
          eyebrow="Cache lab · 0 credits"
          title="Ask the cache what it would do"
          sub="Type any query. It runs the same decision on the live Redis contents and shows the nearest cached queries with their similarity scores. Nothing is sent to SerpApi."
        />
        <CacheLab />
      </section>

      <section className="mt-16">
        <SectionTitle eyebrow="Redis" title="What is cached right now" sub="Raw SerpApi responses, product-page lookups and Gemini spelling decisions, each with its own TTL." />
        <CacheExplorer data={entries} onRefresh={refresh} />
      </section>

      <section className="mt-16">
        <SectionTitle
          eyebrow="Proof"
          title="What the cache has saved since this server started"
          sub="Every number is measured from real calls on this machine, not estimated from a formula."
        />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Stat label="Searches" value={s?.searches ?? 0} />
          <Stat label="SerpApi requests" value={s?.serpapi_calls ?? 0} />
          <Stat label="Credits spent" value={s?.credits_spent ?? 0} tone="miss" />
          <Stat label="Credits saved" value={s?.credits_saved ?? 0} tone="hit" hint={s ? `${s.hit_rate_pct}% hit rate` : undefined} />
          <Stat
            label="Avg latency"
            value={s?.avg_hit_ms != null ? fmtMs(s.avg_hit_ms) : "—"}
            tone="hit"
            hint={s?.avg_api_ms ? `vs ${fmtMs(s.avg_api_ms)} from SerpApi` : "cache hit"}
          />
          <Stat label="Waiting saved" value={s ? fmtMs(s.time_saved_ms) : "—"} tone="sem" hint={`${stats?.cache.cache_size ?? 0} entries in Redis`} />
        </div>
        {account && (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-panel-2 px-4 py-3 text-xs text-muted">
            <Coins className="h-4 w-4 text-miss" />
            SerpApi {account.plan_name}: <span className="tnum text-ink">{account.this_month_usage}</span> of{" "}
            <span className="tnum text-ink">{account.searches_per_month}</span> searches used this month
            <div className="h-1.5 min-w-32 flex-1 rounded-full bg-line">
              <div className="h-1.5 rounded-full bg-miss" style={{ width: `${Math.min(100, (account.this_month_usage / account.searches_per_month) * 100)}%` }} />
            </div>
            <span className="text-faint">live from account.json (costs nothing)</span>
          </div>
        )}
      </section>

      <SiteFooter />
    </main>
  );
}
