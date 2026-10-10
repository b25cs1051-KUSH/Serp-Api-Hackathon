"use client";

import { Loader2, MapPin, Search, ShieldCheck, Stethoscope } from "lucide-react";
import { useEffect, useState } from "react";
import ChooseCard from "@/components/ChooseCard";
import PrescriptionForm, { RX_EXAMPLE } from "@/components/PrescriptionForm";
import SiteFooter from "@/components/shell/SiteFooter";
import ProductCard from "@/components/shop/ProductCard";
import Receipt from "@/components/shop/Receipt";
import ShopHeader, { type ShopTab } from "@/components/shop/ShopHeader";
import OfferColumn from "@/components/shop/OfferColumn";
import { EmptyState, ErrorNote, LoadingCards } from "@/components/shop/ShopStates";
import type { Listing, RxItem } from "@/lib/api";
import { rememberLogos } from "@/lib/logos";
import { buildOffers } from "@/lib/offers";
import { usePrescription } from "@/lib/usePrescription";
import { useSearch } from "@/lib/useSearch";

/** Popular examples; cache contents and available credits change over time. */
const EXAMPLES = ["Atorbest 10", "Stamlo 5", "Dolo 650", "Telma 40", "Pan 40"];

/** The shop: one medicine or a whole prescription, priced delivered to the PIN. No calls, credits or cache here. */
export default function ShopView() {
  const [tab, setTab] = useState<ShopTab>("one");
  const [query, setQuery] = useState("");
  const [pincode, setPincode] = useState("110001");
  const [rxItems, setRxItems] = useState<RxItem[]>(RX_EXAMPLE);

  // /shop?tab=rx opens the prescription tab (read after mount so the static page stays the same for everyone).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") !== "rx") return;
    const t = setTimeout(() => setTab("rx"), 0);
    return () => clearTimeout(t);
  }, []);

  // One-medicine searches resolve the top listings' product pages; prescriptions don't (as before the redesign).
  const { state, run } = useSearch();
  const running = state.status === "running";
  const rx = usePrescription();
  const rxRunning = rx.state.status === "running";

  const search = (q = query) => {
    const text = q.trim();
    if (!text || running || pincode.length !== 6) return;
    setQuery(text);
    setTab("one");
    run(text, pincode, true);
  };
  const submitRx = (items: RxItem[] = rxItems) => {
    const clean = items.map((it) => ({ q: it.q.trim().replace(/\s+/g, " "), tablets: it.tablets })).filter((it) => it.q.length >= 2);
    if (!clean.length || rxRunning || pincode.length !== 6) return;
    rx.run(clean, pincode, false);
  };
  const pickRx = (line: number, q: string) => {
    const items = rx.state.items.map((it, i) => (i === line ? { ...it, q } : it));
    setRxItems(items);
    rx.run(items, rx.state.pincode, false);
  };

  const listings = state.listings ?? [];
  // Store icons from every result, so basket orders and swaps show the same pharmacy logos.
  rememberLogos(listings);
  rememberLogos(state.alternatives ? [...state.alternatives.cheaper_alternatives, ...state.alternatives.other_alternatives] : []);
  for (const l of Object.values(rx.state.lines)) {
    rememberLogos(l.listings);
    if (l.alternatives) rememberLogos([...l.alternatives.cheaper_alternatives, ...l.alternatives.other_alternatives]);
  }
  const zone = state.pincode === pincode ? listings[0]?.pincode_zone : undefined;
  const name = state.alternatives?.matched_brand ?? state.query;
  const pending = (l: Listing) => state.links && !state.linksResolved && listings.indexOf(l) < 5;
  const offers = buildOffers(name, listings, state.alternatives);
  const own = offers.filter((o) => !o.isSwap);
  const swaps = offers.filter((o) => o.isSwap);
  const alts = state.alternatives;
  const notSold = alts?.not_found ?? [];

  return (
    <div className="theme-light min-h-screen w-full">
      <ShopHeader tab={tab} onTab={setTab} pincode={pincode} setPincode={setPincode} zone={zone} onEnter={() => (tab === "one" ? search() : submitRx())} />

      <main className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-6">
        {tab === "one" ? (
          <div id="panel-one" role="tabpanel" aria-labelledby="tab-one" className="py-6">
            {state.status === "idle" && <EmptyState onPaste={() => setTab("rx")} />}
            <form
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                search();
              }}
              className="surface flex gap-2 p-3"
            >
              <div className="relative min-w-0 flex-1">
                <Search aria-hidden className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
                <label className="sr-only" htmlFor="q">Medicine name</label>
                <input
                  id="q"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search a medicine, e.g. Dolo 650"
                  className="w-full rounded-lg border border-line bg-panel-2 py-3 pl-9 pr-3 text-base outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-hit placeholder:text-faint focus:border-accent"
                />
              </div>
              <button
                disabled={running || !query.trim() || pincode.length !== 6}
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
              >
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search aria-hidden className="h-4 w-4" />}
                Search
              </button>
            </form>

            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 px-1 text-xs text-muted" aria-label="Popular searches">
              <span className="font-medium">Popular:</span>
              {EXAMPLES.map((e) => (
                <button
                  key={e}
                  type="button"
                  onClick={() => search(e)}
                  disabled={running}
                  className="rounded-full border border-line/80 bg-panel/70 px-2.5 py-0.5 hover:border-accent/50 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50"
                >
                  {e}
                </button>
              ))}
            </div>

            {state.status !== "idle" && (
              <section className="mt-6 space-y-5">
                {state.error && <ErrorNote message={state.error} />}
                {state.choose ? (
                  <ChooseCard choose={state.choose} onPick={search} />
                ) : (
                  <>
                    {state.alternatives && state.alternatives.matched_by !== "exact" && (
                      <p className="text-sm text-muted">
                        Showing results for <span className="font-medium text-ink">{state.alternatives.matched_brand ?? state.alternatives.composition.name}</span> (you
                        typed &ldquo;{state.query}&rdquo;).
                      </p>
                    )}
                    {state.listings === null ? (
                      state.status === "running" && <LoadingCards waking={state.waking} />
                    ) : listings.length === 0 ? (
                      <p className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">
                        No listing is exactly {state.query}. Look-alike products were left out on purpose.
                      </p>
                    ) : (
                      <>
                        <ProductCard name={name} listings={listings} reference={alts?.reference} pending={pending} />

                        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 lg:grid-cols-2">
                          <OfferColumn
                            id="own-title"
                            title={name}
                            offers={own}
                            pending={pending}
                            empty="Not sold online for this PIN right now."
                            sub={
                              <span className="flex flex-wrap items-center gap-1.5">
                                <MapPin aria-hidden className="h-3 w-3" /> Every pharmacy, cheapest per tablet first, delivered to {state.pincode}
                                {zone && <span className="rounded bg-panel px-1.5 text-[10px] uppercase tracking-wide text-faint ring-1 ring-line">{zone}</span>}
                              </span>
                            }
                          />
                          <OfferColumn
                            id="alt-title"
                            title="Alternative medicines"
                            offers={swaps}
                            empty={
                              alts === undefined && running
                                ? "Looking for alternative medicines…"
                                : alts === null
                                  ? "We couldn't identify this medicine, so no alternatives are suggested."
                                  : "No alternative medicines found online for this PIN."
                            }
                            sub={
                              alts?.composition ? (
                                <>
                                  {alts.composition.name}
                                  {alts.composition.brand_count != null && ` · ${swaps.length} of ${alts.composition.brand_count} brands found online`}
                                </>
                              ) : undefined
                            }
                          >
                            {alts === null && (
                              <p className="flex items-center gap-1.5">
                                <ShieldCheck className="h-3.5 w-3.5" /> We never guess on medicines.
                              </p>
                            )}
                            {notSold.length > 0 && <p>Not sold online for this PIN right now: {notSold.join(", ")}.</p>}
                            {alts && (
                              <p className="flex items-center gap-1.5 font-medium text-[#854d0e]">
                                <Stethoscope className="h-3.5 w-3.5" /> Same strength and form. Ask your doctor or pharmacist before switching.
                              </p>
                            )}
                          </OfferColumn>
                        </div>
                      </>
                    )}
                  </>
                )}
              </section>
            )}
          </div>
        ) : (
          <div id="panel-rx" role="tabpanel" aria-labelledby="tab-rx" className="py-6">
            <h1 className="max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">Your prescription</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
              Enter or paste your medicines below, with optional tablet counts, and set your 6-digit delivery PIN.
              Compare complete baskets, delivery included, for your prescribed brands and alternatives with the same salt, strength and form.
            </p>
            <PrescriptionForm colorKits items={rxItems} setItems={setRxItems} pincode={pincode} setPincode={setPincode} running={rxRunning} onSubmit={() => submitRx()} />
            {rx.state.status !== "idle" && (
              <div className="mt-8">
                <Receipt rx={rx.state} onPick={pickRx} />
              </div>
            )}
          </div>
        )}
        <SiteFooter />
      </main>
    </div>
  );
}
