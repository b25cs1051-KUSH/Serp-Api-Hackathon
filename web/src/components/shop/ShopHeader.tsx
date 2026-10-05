"use client";

import { Loader2, MapPin, Search, ShoppingCart } from "lucide-react";
import Link from "next/link";

const ZONE: Record<string, string> = { metro: "Metro", tier2: "Tier 2", tier3: "Tier 3", remote: "Remote", unserviceable: "No delivery" };

/** Shop header: logo (home), the medicine search, the delivery PIN (with its zone once known) and the cart. */
export default function ShopHeader({
  query,
  setQuery,
  pincode,
  setPincode,
  zone,
  running,
  onSearch,
  cartCount,
  onCart,
}: {
  query: string;
  setQuery: (q: string) => void;
  pincode: string;
  setPincode: (p: string) => void;
  zone?: string;
  running: boolean;
  onSearch: () => void;
  cartCount: number;
  onCart: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-2 px-4 py-3 sm:flex-nowrap sm:gap-3 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2 rounded-lg focus-visible:outline-2 focus-visible:outline-accent" aria-label="PharmaWatch home">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-black text-white">P</span>
          <span className="hidden font-semibold sm:inline">PharmaWatch</span>
        </Link>

        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            onSearch();
          }}
          className="order-3 flex w-full min-w-0 items-center gap-2 sm:order-none sm:flex-1"
        >
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <label className="sr-only" htmlFor="q">Medicine name</label>
            <input
              id="q"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search a medicine, e.g. Dolo 650"
              className="w-full rounded-lg border border-line bg-panel py-2.5 pl-9 pr-3 text-sm outline-none placeholder:text-faint focus:border-accent"
            />
          </div>
          <button
            disabled={running || !query.trim() || pincode.length !== 6}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            <span className="sr-only sm:not-sr-only">Search</span>
          </button>
        </form>

        <div className="ml-auto flex shrink-0 items-center gap-2 sm:ml-0">
          <div className="relative">
            <MapPin className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <label className="sr-only" htmlFor="pin">Delivery PIN code</label>
            <input
              id="pin"
              value={pincode}
              onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              onKeyDown={(e) => e.key === "Enter" && onSearch()}
              inputMode="numeric"
              placeholder="PIN"
              className={`tnum rounded-lg border border-line bg-panel py-2.5 pl-8 pr-2 font-mono text-sm outline-none focus:border-accent ${zone ? "w-40" : "w-28"}`}
            />
            {zone && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted">· {ZONE[zone] ?? zone}</span>}
          </div>
          <button
            type="button"
            onClick={onCart}
            className="relative flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-2.5 text-sm font-medium hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-accent"
            aria-label={`Cart, ${cartCount} medicine${cartCount === 1 ? "" : "s"}`}
          >
            <ShoppingCart className="h-4 w-4" />
            <span className="hidden sm:inline">Cart</span>
            {cartCount > 0 && <span className="tnum grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] font-semibold text-white">{cartCount}</span>}
          </button>
        </div>
      </div>
    </header>
  );
}
