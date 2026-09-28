"use client";

import { FlaskRound, Loader2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { fmtMs, getJSON, type LabResult } from "@/lib/api";

const EXAMPLES = ["Stamlo 5 tablet", "Dolo 500", "dolo 650 MG", "Crocin 650", "atorvastatin 10 mg"];

const VERDICT = {
  exact_hit: { label: "EXACT HIT", cls: "text-hit bg-hit/10 ring-hit/30" },
  semantic_hit: { label: "SEMANTIC HIT", cls: "text-sem bg-sem/10 ring-sem/30" },
  api_call: { label: "API CALL", cls: "text-miss bg-miss/10 ring-miss/30" },
};

export default function CacheLab() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<LabResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const test = async (text: string) => {
    if (!text.trim()) return;
    setQ(text);
    setLoading(true);
    setErr(null);
    try {
      setRes(await getJSON<LabResult>(`/api/cache/lab?q=${encodeURIComponent(text)}&top=6`));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const v = res ? VERDICT[res.decision] : null;

  return (
    <div className="card p-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          test(q);
        }}
        className="flex flex-col gap-2 sm:flex-row"
      >
        <div className="relative flex-1">
          <FlaskRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Type any medicine query. Nothing is searched, 0 credits"
            className="w-full rounded-lg border border-line bg-bg py-2.5 pl-9 pr-3 text-sm outline-none placeholder:text-faint focus:border-sem/60"
          />
        </div>
        <button className="rounded-lg bg-sem/15 px-4 py-2.5 text-sm font-medium text-sem ring-1 ring-sem/30 hover:bg-sem/25 disabled:opacity-50" disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Ask the cache"}
        </button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((e) => (
          <button key={e} onClick={() => test(e)} className="rounded-full border border-line px-2.5 py-0.5 text-[11px] text-muted hover:border-sem/40 hover:text-ink">
            {e}
          </button>
        ))}
      </div>

      {err && <p className="mt-4 text-sm text-bad">{err}</p>}

      {res && v && (
        <div className="rise mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div>
            <span className={`inline-flex rounded-lg px-3 py-1.5 text-sm font-bold tracking-wide ring-1 ${v.cls}`}>{v.label}</span>
            <p className="mt-3 text-sm text-ink">{res.reason}</p>
            <dl className="mt-4 space-y-1.5 text-xs">
              <Row k="cache sees" v={<span className="font-mono">{res.normalized_query.split(" | ")[0]}</span>} />
              <Row k="cache key" v={<span className="font-mono">{res.cache_key}</span>} />
              <Row k="cost if searched" v={<span className={res.credits ? "text-miss" : "text-hit"}>{res.credits ? "1 credit" : "0 credits"}</span>} />
              <Row k="exact lookup" v={fmtMs(res.timings_ms.exact_lookup)} />
              <Row k="embedding" v={fmtMs(res.timings_ms.embed)} />
              <Row k={`scan ${res.compared_against} vectors`} v={fmtMs(res.timings_ms.scan)} />
            </dl>
          </div>

          <div>
            <div className="mb-2 flex justify-between text-[11px] text-faint">
              <span>nearest cached queries</span>
              <span>cosine similarity · threshold {res.threshold}</span>
            </div>
            <div className="space-y-2">
              {res.nearest.map((n, i) => {
                const blocked = n.above_threshold && n.dosage_guard_blocks;
                const color = !n.above_threshold ? "bg-faint/50" : blocked ? "bg-bad" : "bg-sem";
                return (
                  <div key={n.query_text + i} className="rise" style={{ animationDelay: `${i * 40}ms` }}>
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate font-mono text-muted">{n.query_text.split(" | ")[0]}</span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        {blocked && (
                          <span className="flex items-center gap-0.5 text-[10px] font-semibold text-bad">
                            <ShieldAlert className="h-3 w-3" /> DOSE GUARD
                          </span>
                        )}
                        <span className={`tnum font-mono ${n.above_threshold && !blocked ? "text-sem" : "text-faint"}`}>{n.similarity.toFixed(3)}</span>
                      </span>
                    </div>
                    <div className="relative mt-1 h-2 rounded-full bg-line/60">
                      <div className={`h-2 rounded-full ${color}`} style={{ width: `${Math.max(0, n.similarity) * 100}%` }} />
                      <div className="absolute -top-0.5 h-3 w-px bg-ink/70" style={{ left: `${res.threshold * 100}%` }} />
                    </div>
                  </div>
                );
              })}
              {res.nearest.length === 0 && <p className="text-xs text-faint">Cache is empty.</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line/50 pb-1">
      <dt className="text-faint">{k}</dt>
      <dd className="tnum text-right text-ink">{v}</dd>
    </div>
  );
}
