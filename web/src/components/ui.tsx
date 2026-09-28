import type { ReactNode } from "react";
import type { CallKind } from "@/lib/api";

export const KIND_STYLE: Record<CallKind, { label: string; text: string; bg: string; bar: string }> = {
  exact: { label: "EXACT HIT", text: "text-hit", bg: "bg-hit/10 ring-hit/30", bar: "bg-hit" },
  semantic: { label: "SEMANTIC HIT", text: "text-sem", bg: "bg-sem/10 ring-sem/30", bar: "bg-sem" },
  api: { label: "API CALL", text: "text-miss", bg: "bg-miss/10 ring-miss/30", bar: "bg-miss" },
  passthrough: { label: "PASSTHROUGH", text: "text-bad", bg: "bg-bad/10 ring-bad/30", bar: "bg-bad" },
};

export function KindBadge({ kind, similarity }: { kind: CallKind; similarity?: number | null }) {
  const s = KIND_STYLE[kind];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ring-1 ${s.text} ${s.bg}`}>
      {s.label}
      {kind === "semantic" && similarity != null && <span className="tnum font-mono">{similarity.toFixed(3)}</span>}
    </span>
  );
}

export function Pill({ ok, children, title }: { ok: boolean | null; children: ReactNode; title?: string }) {
  const dot = ok == null ? "bg-faint pulse-dot" : ok ? "bg-hit" : "bg-bad";
  return (
    <span title={title} className="inline-flex items-center gap-2 rounded-full border border-line bg-panel-2 px-3 py-1 text-xs text-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {children}
    </span>
  );
}

export function SectionTitle({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: ReactNode }) {
  return (
    <div className="mb-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-hit">{eyebrow}</div>
      <h2 className="mt-1 text-xl font-semibold text-ink">{title}</h2>
      {sub && <p className="mt-1 max-w-3xl text-sm text-muted">{sub}</p>}
    </div>
  );
}

export function Stat({ label, value, hint, tone = "ink" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "ink" | "hit" | "miss" | "sem" }) {
  const color = { ink: "text-ink", hit: "text-hit", miss: "text-miss", sem: "text-sem" }[tone];
  return (
    <div className="rounded-xl border border-line bg-panel-2 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-faint">{label}</div>
      <div className={`tnum mt-1 text-2xl font-semibold ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted">{hint}</div>}
    </div>
  );
}
