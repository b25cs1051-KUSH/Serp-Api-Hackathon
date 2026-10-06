"use client";

import { ClipboardList, MapPin, Pill } from "lucide-react";
import Link from "next/link";

export type ShopTab = "one" | "rx";

const ZONE: Record<string, string> = { metro: "Metro", tier2: "Tier 2", tier3: "Tier 3", remote: "Remote", unserviceable: "No delivery" };

/** Shop header: logo (home), One medicine / Whole prescription, and the delivery PIN (with its zone once known). */
export default function ShopHeader({
  tab,
  onTab,
  pincode,
  setPincode,
  zone,
  onEnter,
}: {
  tab: ShopTab;
  onTab: (t: ShopTab) => void;
  pincode: string;
  setPincode: (p: string) => void;
  zone?: string;
  onEnter: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-2 px-4 py-3 sm:flex-nowrap sm:gap-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2 rounded-lg focus-visible:outline-2 focus-visible:outline-accent">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-black text-white">P</span>
          <span className="sr-only font-semibold sm:not-sr-only">PharmaWatch</span>
        </Link>

        <div role="tablist" aria-label="What to search" className="order-3 flex w-full rounded-xl border border-line bg-panel-2 p-1 text-sm sm:order-none sm:w-auto">
          {([
            ["one", "One medicine", Pill],
            ["rx", "Whole prescription", ClipboardList],
          ] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              onClick={() => onTab(id)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 font-medium focus-visible:outline-2 focus-visible:outline-accent sm:flex-none ${
                tab === id ? "bg-accent text-white" : "text-muted hover:text-ink"
              }`}
            >
              <Icon aria-hidden className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>

        <div className="relative ml-auto shrink-0">
          <MapPin aria-hidden className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <label className="sr-only" htmlFor="pin">Delivery PIN code</label>
          <input
            id="pin"
            value={pincode}
            onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            onKeyDown={(e) => e.key === "Enter" && onEnter()}
            inputMode="numeric"
            placeholder="PIN"
            className={`tnum rounded-lg border border-line bg-panel py-2.5 pl-8 pr-2 font-mono text-sm outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-hit focus:border-accent ${zone ? "w-40" : "w-28"}`}
          />
          {zone && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted">· {ZONE[zone] ?? zone}</span>}
        </div>
      </div>
    </header>
  );
}
