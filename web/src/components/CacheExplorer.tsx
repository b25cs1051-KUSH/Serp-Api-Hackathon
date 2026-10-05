"use client";

import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { fmtBytes, fmtTtl, type CacheEntries } from "@/lib/api";

const KIND = {
  shopping: { label: "price search", cls: "text-miss bg-miss/10" },
  product_link: { label: "product link", cls: "text-sem bg-sem/10" },
  llm_decision: { label: "Gemini decision", cls: "text-llm bg-llm/10" },
} as const;

export default function CacheExplorer({ data, onRefresh }: { data: CacheEntries | null; onRefresh: () => void }) {
  const [filter, setFilter] = useState<keyof typeof KIND | "all">("all");
  const rows = useMemo(() => (data?.entries ?? []).filter((e) => filter === "all" || e.kind === filter), [data, filter]);

  return (
    <div className="card p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FilterBtn active={filter === "all"} onClick={() => setFilter("all")}>
          all {data?.entries.length ?? 0}
        </FilterBtn>
        {(Object.keys(KIND) as (keyof typeof KIND)[]).map((k) => (
          <FilterBtn key={k} active={filter === k} onClick={() => setFilter(k)}>
            {KIND[k].label} {data?.counts[k] ?? 0}
          </FilterBtn>
        ))}
        <span className="ml-auto text-xs text-faint">{data?.total_bytes ? `${fmtBytes(data.total_bytes)} of SerpApi JSON in Redis` : ""}</span>
        <button onClick={onRefresh} className="rounded-md p-1.5 text-faint ring-1 ring-line hover:text-ink" title="Refresh">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>
      {data && !data.redis_ok ? (
        <p className="text-sm text-bad">Redis is down: the cache is in passthrough mode.</p>
      ) : (
        <div className="max-h-80 overflow-auto">
          <table className="w-full table-fixed text-xs">
            <thead className="sticky top-0 bg-panel">
              <tr className="border-b border-line text-left text-[10px] uppercase tracking-wider text-faint">
                <th className="py-2 pr-3 font-medium">cached query</th>
                <th className="w-28 py-2 pr-3 font-medium">type</th>
                <th className="w-20 py-2 pr-3 text-right font-medium">expires in</th>
                <th className="hidden w-16 py-2 text-right font-medium sm:table-cell">size</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.key} className="border-b border-line/50">
                  <td className="truncate py-1.5 pr-3 font-mono text-muted" title={e.query_text}>
                    {e.kind === "product_link" ? `product page · ${e.key}` : e.query_text.split(" | ")[0]}
                  </td>
                  <td className="py-1.5 pr-3">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${KIND[e.kind].cls}`}>{KIND[e.kind].label}</span>
                  </td>
                  <td className="tnum py-1.5 pr-3 text-right text-muted">{fmtTtl(e.ttl_s)}</td>
                  <td className="tnum hidden py-1.5 text-right text-faint sm:table-cell">{fmtBytes(e.bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FilterBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs ring-1 transition ${active ? "bg-ink text-bg ring-ink" : "text-muted ring-line hover:text-ink"}`}
    >
      {children}
    </button>
  );
}
