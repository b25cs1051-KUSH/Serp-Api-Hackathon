"use client";

import { ClipboardList, Coins, Cpu, Link2, Loader2, MapPin, Pill as PillIcon, Repeat, Search, ShoppingBag } from "lucide-react";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import Alternatives from "@/components/Alternatives";
import AnswerCard from "@/components/AnswerCard";
import BasketCard from "@/components/BasketCard";
import PrescriptionForm, { RX_EXAMPLE } from "@/components/PrescriptionForm";
import ChooseCard from "@/components/ChooseCard";
import CacheExplorer from "@/components/CacheExplorer";
import CacheFlow from "@/components/CacheFlow";
import CacheLab from "@/components/CacheLab";
import Results from "@/components/Results";
import UnderTheHood from "@/components/UnderTheHood";
import { Pill, SectionTitle, Stat } from "@/components/ui";
import { fmtMs, getJSON, type Account, type CacheEntries, type Health, type RxItem, type Stats } from "@/lib/api";
import { asSearchState, usePrescription } from "@/lib/usePrescription";
import { useSearch } from "@/lib/useSearch";

const EXAMPLES = ["Stamlo 5", "Dolo 650", "Glyciphage SR 500", "Atorvastatin 10mg", "Pan-D"];

/** "shop": the product as a user sees it. "engine": the same search with every SerpApi call, cache decision and credit shown. */
type View = "shop" | "engine";
const VIEW_KEY = "pharmawatch-view";

const VIEW_EVENT = "pharmawatch-view-change";
let sessionView: View | null = null; // used when storage is blocked

/** ?view=engine in the URL wins (a link for judges), then the last choice in this browser. */
function readView(): View {
  const fromUrl = new URLSearchParams(window.location.search).get("view");
  if (fromUrl === "engine" || fromUrl === "shop") return fromUrl;
  if (sessionView) return sessionView;
  try {
    return localStorage.getItem(VIEW_KEY) === "engine" ? "engine" : "shop";
  } catch {
    return "shop";
  }
}

function subscribeView(onChange: () => void) {
  window.addEventListener(VIEW_EVENT, onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener(VIEW_EVENT, onChange);
    window.removeEventListener("popstate", onChange);
  };
}

function setView(v: View) {
  sessionView = v;
  try {
    localStorage.setItem(VIEW_KEY, v);
  } catch {
    /* storage blocked: the choice lasts for this visit */
  }
  const url = new URL(window.location.href);
  if (v === "engine") url.searchParams.set("view", "engine");
  else url.searchParams.delete("view");
  window.history.replaceState(null, "", url);
  window.dispatchEvent(new Event(VIEW_EVENT));
}

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [entries, setEntries] = useState<CacheEntries | null>(null);

  const [query, setQuery] = useState("");
  const [pincode, setPincode] = useState("110001");
  const [links, setLinks] = useState(true);
  // The server render can't see the URL or storage, so it renders "shop"; the browser then reads the real view.
  const view = useSyncExternalStore(subscribeView, readView, () => "shop" as View);
  const engine = view === "engine";

  const refresh = useCallback(() => {
    getJSON<Stats>("/api/stats").then(setStats).catch(() => {});
    getJSON<CacheEntries>("/api/cache/entries").then(setEntries).catch(() => {});
    getJSON<Account>("/api/account").then(setAccount).catch(() => {});
  }, []);

  const { state, run } = useSearch(refresh);
  const running = state.status === "running";
  const [mode, setMode] = useState<"one" | "rx">("one");
  const [rxItems, setRxItems] = useState<RxItem[]>(RX_EXAMPLE);
  const rx = usePrescription(refresh);
  const rxRunning = rx.state.status === "running";
  const submitRx = (items = rxItems) => {
    const clean = items.map((it) => ({ q: it.q.trim().replace(/\s+/g, " "), tablets: it.tablets })).filter((it) => it.q.length >= 2);
    if (!clean.length || rxRunning) return;
    rx.run(clean, pincode, links && engine);
  };
  const pickRx = (line: number, q: string) => {
    const items = rx.state.items.map((it, i) => (i === line ? { ...it, q } : it));
    setRxItems(items);
    rx.run(items, rx.state.pincode, links && engine);
  };

  useEffect(() => {
    let stop = false;
    const poll = () =>
      getJSON<Health>("/api/health")
        .then((h) => {
          setHealth(h);
          setHealthErr(false);
          if (!stop && h.model !== "ready") setTimeout(poll, 2000);
        })
        .catch(() => {
          setHealthErr(true);
          if (!stop) setTimeout(poll, 3000);
        });
    poll();
    refresh();
    return () => {
      stop = true;
    };
  }, [refresh]);

  const submit = (q = query) => {
    const text = q.trim();
    if (!text || running) return;
    setQuery(text);
    run(text, pincode, links);
  };

  const s = stats?.session;

  return (
    <main className="mx-auto w-full max-w-7xl px-4 pb-24 sm:px-6">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 py-5">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-hit to-sem text-sm font-black text-bg">P</div>
          <div>
            <div className="font-semibold leading-tight">PharmaWatch</div>
            <div className="text-[11px] text-faint">{engine ? "SerpApi · Redis semantic cache · Gemini" : "Medicine prices, delivered"}</div>
          </div>
        </div>
        <ViewToggle view={view} onChange={setView} />
      </header>

      {engine && (
        <div className="-mt-1 flex flex-wrap justify-end gap-2">
          {healthErr ? (
            <Pill ok={false}>API offline: start uvicorn on :8000</Pill>
          ) : (
            <>
              <Pill ok={health ? health.redis_ok : null} title={health?.redis}>
                Redis {health ? (health.redis_ok ? "connected" : "down: passthrough") : "…"}
              </Pill>
              <Pill ok={health ? (health.model === "ready" ? true : health.model === "failed" ? false : null) : null}>
                Embedding model {health?.model === "ready" ? `warm${health.model_warm_ms ? ` (${fmtMs(health.model_warm_ms)} at boot)` : ""}` : health?.model ?? "…"}
              </Pill>
              <Pill ok={account ? account.total_searches_left > 20 : null} title="Live from SerpApi account.json (free)">
                SerpApi {account ? `${account.total_searches_left} / ${account.searches_per_month} credits left` : "…"}
              </Pill>
              <Pill ok={health ? health.gemini_key_configured : null}>Gemini {health?.gemini_key_configured ? "on" : "off"}</Pill>
            </>
          )}
        </div>
      )}

      {/* Hero + search */}
      <section className="pt-8 pb-8">
        <h1 className="max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
          The real price of your medicine, <span className="bg-gradient-to-r from-hit to-sem bg-clip-text text-transparent">delivered to your PIN</span>.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {engine
            ? "Compares 1mg, PharmEasy, Netmeds, Apollo and Medplus including delivery fees, suggests only verified same-composition generics, and never pays SerpApi twice for the same question."
            : "Compare 1mg, PharmEasy, Apollo, Medplus and more with delivery to your PIN included, and see cheaper brands with the same salt."}
        </p>

        <div role="group" aria-label="What to search" className="mt-6 inline-flex rounded-xl border border-line bg-panel-2 p-1 text-sm">
          {([
            ["one", "One medicine", PillIcon],
            ["rx", "Whole prescription", ClipboardList],
          ] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              aria-pressed={mode === id}
              onClick={() => setMode(id)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${mode === id ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}
            >
              <Icon className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>

        {mode === "rx" && (
          <PrescriptionForm items={rxItems} setItems={setRxItems} pincode={pincode} setPincode={setPincode} running={rxRunning} onSubmit={() => submitRx()} />
        )}

        {mode === "one" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="card mt-3 flex flex-col gap-2 p-2 md:flex-row"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Medicine name, e.g. Dolo 650"
              className="w-full rounded-lg bg-transparent py-3 pl-10 pr-3 text-base outline-none placeholder:text-faint"
            />
          </div>
          <div className="relative md:w-36">
            <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <input
              value={pincode}
              onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              placeholder="PIN"
              className="tnum w-full rounded-lg border border-line bg-bg py-3 pl-9 pr-3 font-mono text-sm outline-none focus:border-hit/50"
            />
          </div>
          <button
            disabled={running || !query.trim() || pincode.length !== 6}
            className="flex items-center justify-center gap-2 rounded-lg bg-hit px-6 py-3 text-sm font-semibold text-bg transition hover:brightness-110 disabled:opacity-40"
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Compare
          </button>
        </form>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {mode === "one" && <span className="text-[11px] text-faint">try:</span>}
          {mode === "one" && EXAMPLES.map((e) => (
            <button key={e} onClick={() => submit(e)} disabled={running} className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-hit/40 hover:text-ink disabled:opacity-40">
              {e}
            </button>
          ))}
          {engine && (
            <label className="ml-auto flex cursor-pointer items-center gap-2 text-xs text-muted" title="Resolves each top listing's own pharmacy product page: 1 SerpApi call per link the first time, then cached.">
              <input type="checkbox" checked={links} onChange={(e) => setLinks(e.target.checked)} className="accent-[#34d399]" />
              <Link2 className="h-3.5 w-3.5" /> resolve direct pharmacy links
            </label>
          )}
        </div>
      </section>

      {/* Results + under the hood */}
      {mode === "rx" && rx.state.status !== "idle" && !engine && (
        <section className="space-y-5">
          {rx.state.error && <div className="card border-bad/40 p-4 text-sm text-bad">{rx.state.error}</div>}
          <BasketCard basket={rx.state.basket} lines={rx.state.lines} items={rx.state.items} running={rxRunning} onPick={pickRx} />
        </section>
      )}

      {mode === "rx" && rx.state.status !== "idle" && engine && (
        <section className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            {rx.state.error && <div className="card border-bad/40 p-4 text-sm text-bad">{rx.state.error}</div>}
            <BasketCard basket={rx.state.basket} lines={rx.state.lines} items={rx.state.items} running={rxRunning} onPick={pickRx} />
          </div>
          <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
            <UnderTheHood
              state={asSearchState(rx.state)}
              note={rx.state.basket ? `Basket optimiser: ${rx.state.basket.stats.combinations.toLocaleString("en-IN")} ways to buy it priced with each pharmacy's delivery rules in ${fmtMs(rx.state.basket.stats.ms)}` : undefined}
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

      {mode === "one" && state.status !== "idle" && !engine && (
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

      {mode === "one" && state.status !== "idle" && engine && (
        <section className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            {state.error && <div className="card border-bad/40 p-4 text-sm text-bad">{state.error}</div>}
            {state.choose ? (
              <ChooseCard choose={state.choose} onPick={submit} />
            ) : (
              <>
                {!(state.status === "error" && state.listings === null) && (
                  <Results listings={state.listings} query={state.query} pincode={state.pincode} linksResolved={state.linksResolved} wantLinks={state.links} />
                )}
                <Alternatives result={state.alternatives} running={running} />
              </>
            )}
          </div>
          <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
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

      {engine && (
      <>
      {/* Session totals */}
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

      {/* How it works */}
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
      </>
      )}

      {!engine && (
        <button
          onClick={() => setView("engine")}
          className="mt-16 flex w-full flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-panel-2 px-5 py-4 text-left text-sm text-muted hover:border-sem/40 hover:text-ink"
        >
          <span>
            <span className="font-medium text-ink">Curious how this works?</span> See every live search, cache hit and credit behind these prices.
          </span>
          <span className="flex items-center gap-1.5 font-medium text-sem">
            <Cpu className="h-4 w-4" /> Under the hood
          </span>
        </button>
      )}

      <footer className="mt-20 border-t border-line pt-6 text-xs text-faint">
        PharmaWatch · prices from Google Shopping via SerpApi · delivery rules per platform and PIN zone · substitutes limited to the same salt, strength and form (Indian Medicine Dataset, MIT). Not medical advice.
      </footer>
    </main>
  );
}

function ViewToggle({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  const options: { id: View; label: string; icon: typeof Cpu }[] = [
    { id: "shop", label: "Shop", icon: ShoppingBag },
    { id: "engine", label: "Under the hood", icon: Cpu },
  ];
  return (
    <div role="group" aria-label="View" className="flex rounded-xl border border-line bg-panel-2 p-1">
      {options.map(({ id, label, icon: Icon }) => {
        const active = view === id;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(id)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-hit ${
              active ? (id === "shop" ? "bg-hit text-bg" : "bg-sem text-bg") : "text-muted hover:text-ink"
            }`}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        );
      })}
    </div>
  );
}
