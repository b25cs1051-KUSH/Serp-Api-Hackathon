import { inr } from "@/lib/api";
import { DEMO, recordedLabel } from "./demo";

/** The hero's saving figure, from the recorded run (never estimated). */
export default function HeroSaving() {
  const best = DEMO.basket.with_swaps.best;
  const prescribed = DEMO.basket.as_prescribed.best;
  if (!best || !prescribed || prescribed.total <= best.total) return null;
  return (
    <div className="rounded-xl border border-line bg-panel p-6">
      <div className="tnum font-mono text-4xl font-semibold text-hit sm:text-5xl">{inr(prescribed.total - best.total)}</div>
      <p className="mt-2 text-sm text-ink">
        less than the prescribed brands ({inr(prescribed.total)}) for {DEMO.items.length} medicines, delivered to {DEMO.pincode}: the cheapest basket is{" "}
        <span className="tnum font-mono">{inr(best.total)}</span>.
      </p>
      <p className="mt-3 text-[11px] text-faint">{recordedLabel(DEMO)}.</p>
    </div>
  );
}
