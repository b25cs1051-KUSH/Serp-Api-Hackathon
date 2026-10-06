"use client";

import { ClipboardList, MapPin, Pill } from "lucide-react";
import { Logo, SiteNav } from "@/components/shell/SiteHeader";

export type ShopTab = "one" | "rx";

const ZONE: Record<string, string> = { metro: "Metro", tier2: "Tier 2", tier3: "Tier 3", remote: "Remote", unserviceable: "No delivery" };

/** Shop header: logo and site navigation, then One medicine / Whole prescription and the delivery PIN. */
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
    <header className="z-30 border-b border-line bg-panel sm:sticky sm:top-0 shadow-[0_1px_0_rgba(0,0,0,0.02),0_4px_16px_-12px_rgba(15,40,35,0.35)]">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3 py-3">
          <Logo />
          <SiteNav />
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-line py-2.5">
          <div role="tablist" aria-label="What to search" className="flex w-full rounded-xl bg-panel-2 p-1 text-sm ring-1 ring-line sm:w-auto">
            {([
              ["one", "One medicine", Pill],
              ["rx", "Prescription", ClipboardList],
            ] as const).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                role="tab"
                id={`tab-${id}`}
                aria-selected={tab === id}
                aria-controls={`panel-${id}`}
                aria-label={id === "rx" ? "Whole prescription" : label}
                onClick={() => onTab(id)}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-4 py-2 font-semibold focus-visible:outline-2 focus-visible:outline-accent sm:flex-none ${
                  tab === id ? "bg-accent text-white shadow-sm" : "text-muted hover:text-ink"
                }`}
              >
                <Icon aria-hidden className="h-4 w-4" /> {id === "rx" && <span className="hidden sm:inline">Whole</span>}
                {id === "rx" ? <span className="sm:lowercase">{label}</span> : label}
              </button>
            ))}
          </div>

          <div className="relative ml-auto flex shrink-0 items-center gap-2">
            <label className="text-xs font-medium text-muted" htmlFor="pin">Deliver to</label>
            <div className="relative">
              <MapPin aria-hidden className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-accent" />
              <input
                id="pin"
                value={pincode}
                onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                onKeyDown={(e) => e.key === "Enter" && onEnter()}
                inputMode="numeric"
                placeholder="PIN"
                aria-label="Delivery PIN code"
                className={`tnum rounded-lg border border-line bg-panel py-2 pl-8 pr-2 font-mono text-sm outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-1 focus-visible:outline-accent focus:border-accent ${zone ? "w-40" : "w-28"}`}
              />
              {zone && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted">· {ZONE[zone] ?? zone}</span>}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
