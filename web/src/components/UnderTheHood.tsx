"use client";

import { Activity, Coins, Gauge, Zap } from "lucide-react";
import { fmtMs } from "@/lib/api";
import type { SearchState } from "@/lib/useSearch";
import { KIND_STYLE, KindBadge, Stat } from "./ui";

const STAGE_LABEL: Record<string, string> = {
  main: "prices shown",
  main_update: "list grew",
  alternatives: "generics shown",
  main_links: "links ready",
  basket: "basket ready",
  basket_links: "basket links ready",
};

export default function UnderTheHood({ state, note }: { state: SearchState; note?: string }) {
  const { calls, done, stages, status, alternatives } = state;
  const spent = calls.filter((c) => c.credit).length;
  const saved = calls.filter((c) => c.kind === "exact" || c.kind === "semantic").length;
  const geminiMs = alternatives?.timings?.gemini_ms;

  const total = Math.max(
    done?.total_ms ?? 0,
    ...calls.map((c) => c.start_ms + c.ms),
    ...stages.map((s) => s.at_ms),
    geminiMs ?? 0,
    1,
  );
  const pct = (ms: number) => `${Math.min(100, (ms / total) * 100)}%`;

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-hit" />
          <h3 className="font-semibold">Under the hood</h3>
          <span className="text-xs text-faint">every SerpApi request this search made</span>
        </div>
        {status === "running" && (
          <span className="flex items-center gap-1.5 text-xs text-hit">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-hit" /> live
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Total time" value={done ? fmtMs(done.total_ms) : status === "running" ? "…" : "—"} />
        <Stat label="SerpApi calls" value={calls.length} hint={`${saved} from cache`} />
        <Stat label="Credits spent" value={spent} tone={spent ? "miss" : "hit"} hint={spent ? "cache misses" : "zero cost"} />
        <Stat
          label="Credits saved"
          value={saved}
          tone="hit"
          hint={done && done.est_time_saved_ms ? `≈ ${fmtMs(done.est_time_saved_ms)} of waiting saved` : undefined}
        />
      </div>

      {note && <p className="mt-3 rounded-lg border border-line bg-panel-2 px-3 py-2 text-xs text-muted">{note}</p>}

      {/* Waterfall */}
      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between text-[11px] text-faint">
          <span className="flex items-center gap-1"><Gauge className="h-3 w-3" /> timeline</span>
          <span className="tnum font-mono">0 → {fmtMs(total)}</span>
        </div>
        <div className="relative overflow-hidden rounded-lg border border-line bg-bg/60 p-2">
          {stages.map((s, i) => (
            <div key={`${s.name}-${i}`} className="pointer-events-none absolute top-0 bottom-0 z-10" style={{ left: `calc(${pct(s.at_ms)} * 0.96 + 2%)` }}>
              <div className="h-full border-l border-dashed border-hit/40" />
              {/* Labels of late stages sit left of their line so they stay inside the panel. */}
              <div className={`absolute -top-0.5 whitespace-nowrap rounded bg-panel px-1 text-[9px] text-hit/80 ${s.at_ms / total > 0.6 ? "right-1" : "left-1"}`}>
                {STAGE_LABEL[s.name] ?? s.name}
              </div>
            </div>
          ))}
          <div className="space-y-1 pt-3">
            {geminiMs != null && (
              <Bar label="Gemini · spelling fix" left="0%" width={pct(geminiMs)} color="bg-llm" ms={geminiMs} />
            )}
            {calls.map((c) => (
              <Bar
                key={c.n}
                label={c.tag}
                left={pct(c.start_ms)}
                width={pct(c.ms)}
                color={KIND_STYLE[c.kind].bar}
                ms={c.ms}
              />
            ))}
            {calls.length === 0 && <div className="py-4 text-center text-xs text-faint">{status === "running" ? "waiting for the first call…" : "Run a search to see its calls here."}</div>}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-faint">
          <Legend color="bg-hit" label="exact hit (Redis GET)" />
          <Legend color="bg-sem" label="semantic hit (embedding)" />
          <Legend color="bg-miss" label="SerpApi call · 1 credit" />
          <Legend color="bg-llm" label="Gemini (not SerpApi)" />
        </div>
      </div>

      {/* Call log */}
      <div className="mt-5">
        <div className="mb-2 flex items-center gap-1 text-[11px] text-faint">
          <Zap className="h-3 w-3" /> call log
        </div>
        <div className="max-h-[360px] space-y-1.5 overflow-y-auto pr-1">
          {calls.map((c) => (
            <div key={c.n} className="rise flex items-start gap-3 rounded-lg border border-line bg-panel-2 px-3 py-2">
              <span className="tnum mt-0.5 w-5 shrink-0 text-right font-mono text-[11px] text-faint">{c.n}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <KindBadge kind={c.kind} similarity={c.similarity} />
                  <span className="truncate text-xs text-ink">{c.tag}</span>
                </div>
                <div className="mt-1 truncate font-mono text-[11px] text-muted">
                  <span className="text-faint">{c.engine}</span> · {c.query}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className={`tnum font-mono text-xs ${KIND_STYLE[c.kind].text}`}>{fmtMs(c.ms)}</div>
                <div className="flex items-center justify-end gap-0.5 text-[10px] text-faint">
                  <Coins className="h-2.5 w-2.5" />
                  {c.credit ? "1 credit" : "free"}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Bar({ label, left, width, color, ms }: { label: string; left: string; width: string; color: string; ms: number }) {
  return (
    <div className="group relative h-5" title={`${label} · ${fmtMs(ms)}`}>
      <div className="absolute inset-y-1 rounded-sm bg-line/40" style={{ left: "2%", right: "2%" }} />
      <div
        className={`rise absolute inset-y-1 rounded-sm ${color}`}
        style={{ left: `calc(${left} * 0.96 + 2%)`, width: `max(calc(${width} * 0.96), 3px)` }}
      />
      <span className="pointer-events-none absolute inset-y-0 left-[3%] flex items-center truncate text-[9px] font-medium text-ink/80 mix-blend-difference">
        {label}
      </span>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`h-2 w-2 rounded-sm ${color}`} />
      {label}
    </span>
  );
}
