"use client";

import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import BasketCard from "@/components/BasketCard";
import ChooseCard from "@/components/ChooseCard";
import PrescriptionForm from "@/components/PrescriptionForm";
import SiteFooter from "@/components/shell/SiteFooter";
import ProductCard, { delivered } from "@/components/shop/ProductCard";
import ShopHeader from "@/components/shop/ShopHeader";
import { EmptyState, ErrorNote, FilterChips, LoadingCards, deliveryHours, type Filter } from "@/components/shop/ShopStates";
import SwapSection from "@/components/shop/SwapSection";
import type { Listing, RxItem } from "@/lib/api";
import { useCart } from "@/lib/useCart";
import { usePrescription } from "@/lib/usePrescription";
import { useSearch } from "@/lib/useSearch";

/** Medicines cached on the price engine at the time of writing (0 credits to search). */
const EXAMPLES = ["Atorbest 10", "Stamlo 5", "Dolo 650", "Telma 40", "Pan 40"];
const BLANK: RxItem[] = [{ q: "", tablets: null }];

/** The shop: what a buyer sees. No calls, credits, timings or cache here. */
export default function ShopView() {
  const [query, setQuery] = useState("");
  const [pincode, setPincode] = useState("110001");
  const [view, setView] = useState<"search" | "cart">("search");
  const [filter, setFilter] = useState<Filter>("cheapest");
  const cart = useCart();

  // One-medicine searches resolve the top listings' product pages; prescriptions don't (as before the redesign).
  const { state, run } = useSearch();
  const running = state.status === "running";
  const rx = usePrescription();
  const rxRunning = rx.state.status === "running";

  const search = (q = query) => {
    const text = q.trim();
    if (!text || running || pincode.length !== 6) return;
    setQuery(text);
    setView("search");
    setFilter("cheapest");
    run(text, pincode, true);
  };
  const submitRx = (items: RxItem[] = cart.items) => {
    const clean = items.map((it) => ({ q: it.q.trim().replace(/\s+/g, " "), tablets: it.tablets })).filter((it) => it.q.length >= 2);
    if (!clean.length || rxRunning) return;
    rx.run(clean, pincode, false);
  };
  const pickRx = (line: number, q: string) => {
    const items = rx.state.items.map((it, i) => (i === line ? { ...it, q } : it));
    cart.set(items);
    rx.run(items, rx.state.pincode, false);
  };

  const listings = state.listings ?? [];
  const zone = state.pincode === pincode ? listings[0]?.pincode_zone : undefined;
  const name = state.alternatives?.matched_brand ?? state.query;
  const pending = (l: Listing) => state.links && !state.linksResolved && listings.indexOf(l) < 5;
  const shown =
    filter === "free"
      ? listings.filter((l) => l.delivery_status === "free")
      : filter === "fastest"
        ? [...listings.filter(delivered)].sort((a, b) => deliveryHours(a.estimated_days) - deliveryHours(b.estimated_days) || (a.total_landed_cost ?? 0) - (b.total_landed_cost ?? 0)).concat(listings.filter((l) => !delivered(l)))
        : listings;

  return (
    <div className="theme-light min-h-screen w-full">
      <ShopHeader
        query={query}
        setQuery={setQuery}
        pincode={pincode}
        setPincode={setPincode}
        zone={zone}
        running={running}
        onSearch={() => search()}
        cartCount={cart.count}
        onCart={() => setView("cart")}
      />

      <main className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-6">
        {view === "cart" ? (
          <section className="py-6">
            <button type="button" onClick={() => setView("search")} className="flex items-center gap-1.5 text-sm text-muted hover:text-ink">
              <ArrowLeft className="h-4 w-4" /> Back to search
            </button>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">Your cart</h1>
            <p className="mt-1 text-sm text-muted">Add medicines from search, paste your prescription, or start from a common one.</p>
            <PrescriptionForm
              items={cart.items.length ? cart.items : BLANK}
              setItems={cart.set}
              pincode={pincode}
              setPincode={setPincode}
              running={rxRunning}
              onSubmit={() => submitRx()}
            />
            {rx.state.status !== "idle" && (
              <div className="mt-6 space-y-5">
                {rx.state.error && <ErrorNote message={rx.state.error} />}
                <BasketCard basket={rx.state.basket} lines={rx.state.lines} items={rx.state.items} running={rxRunning} onPick={pickRx} />
              </div>
            )}
          </section>
        ) : state.status === "idle" ? (
          <EmptyState examples={EXAMPLES} onSearch={search} onPaste={() => setView("cart")} />
        ) : (
          <section className="space-y-5 py-6">
            {state.error && <ErrorNote message={state.error} />}
            {state.choose ? (
              <ChooseCard choose={state.choose} onPick={search} />
            ) : (
              <>
                {state.alternatives && state.alternatives.matched_by !== "exact" && (
                  <p className="text-sm text-muted">
                    Showing results for <span className="font-medium text-ink">{state.alternatives.matched_brand ?? state.alternatives.composition.name}</span> (you typed
                    &ldquo;{state.query}&rdquo;).
                  </p>
                )}
                {state.listings === null ? (
                  state.status === "running" && <LoadingCards />
                ) : listings.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-line p-6 text-center text-sm text-muted">
                    No listing is exactly {state.query}. Look-alike products were left out on purpose.
                  </p>
                ) : (
                  <>
                    <FilterChips value={filter} onChange={setFilter} />
                    {filter !== "swaps" &&
                      (shown.length ? (
                        <ProductCard
                          name={name}
                          listings={shown}
                          reference={state.alternatives?.reference}
                          pending={pending}
                          inCart={cart.has(name)}
                          onAdd={(t) => cart.add(name, t)}
                        />
                      ) : (
                        <p className="rounded-xl border border-dashed border-line p-5 text-sm text-muted">
                          No pharmacy delivers {name} free to {state.pincode}. Cheapest delivered is shown under &ldquo;Cheapest delivered&rdquo;.
                        </p>
                      ))}
                  </>
                )}
                <SwapSection
                  result={state.alternatives}
                  running={running}
                  only={(a) => filter !== "free" || a.delivery_status === "free"}
                  hasInCart={cart.has}
                  onAdd={cart.add}
                />
              </>
            )}
          </section>
        )}
        <SiteFooter />
      </main>
    </div>
  );
}
