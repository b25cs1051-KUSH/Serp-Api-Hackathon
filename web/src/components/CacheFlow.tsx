import { ArrowRight, Binary, Database, Hash, ShieldAlert, Sparkles, Zap } from "lucide-react";
import type { ComponentType } from "react";

const STEPS: { icon: ComponentType<{ className?: string }>; title: string; body: string; tone: string; example: string }[] = [
  {
    icon: Sparkles,
    title: "1 · Normalize",
    body: "Lowercase, collapse spaces, glue units to numbers.",
    example: '"Dolo  650 MG" → "dolo 650mg"',
    tone: "text-ink",
  },
  {
    icon: Hash,
    title: "2 · Exact key",
    body: "SHA-256 of the params. One Redis GET, no model: under 5 ms.",
    example: "seen before → EXACT HIT",
    tone: "text-hit",
  },
  {
    icon: Binary,
    title: "3 · Embed + compare",
    body: "MiniLM turns the query into 384 numbers; cosine similarity against every cached query.",
    example: '"stamlo 5 tablet" ≈ "stamlo 5" 0.917',
    tone: "text-sem",
  },
  {
    icon: ShieldAlert,
    title: "4 · Dosage guard",
    body: "Close meaning but different numbers? Never reuse. A wrong dose is worse than a credit.",
    example: '"Dolo 500" vs "Dolo 650" 0.949 → blocked',
    tone: "text-bad",
  },
  {
    icon: Zap,
    title: "5 · SerpApi",
    body: "Only now is a credit spent. The result is written to Redis on a background thread, so the user never waits for it.",
    example: "miss → 1 credit, cached 24 h",
    tone: "text-miss",
  },
];

export default function CacheFlow({ threshold }: { threshold?: number }) {
  return (
    <div className="card p-5">
      <div className="grid gap-3 md:grid-cols-5">
        {STEPS.map((s, i) => (
          <div key={s.title} className="relative rounded-xl border border-line bg-panel-2 p-4">
            <s.icon className={`h-5 w-5 ${s.tone}`} />
            <div className="mt-2 text-sm font-semibold">{s.title}</div>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              {s.body}
              {i === 2 && threshold != null && (
                <>
                  {" "}Hit only if ≥ <span className="tnum font-mono text-sem">{threshold}</span>.
                </>
              )}
            </p>
            <div className="mt-2 rounded-md bg-bg/60 px-2 py-1 font-mono text-[10px] text-faint">{s.example}</div>
            {i < STEPS.length - 1 && (
              <ArrowRight className="absolute -right-3 top-1/2 z-10 hidden h-4 w-4 -translate-y-1/2 text-faint md:block" />
            )}
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-2 text-xs text-muted md:grid-cols-3">
        <Note icon={Database} title="Redis, persistent">
          Survives restarts (AOF), shared by every process, native TTL: prices 24 h, product links 24 h, Gemini decisions 30 days.
        </Note>
        <Note icon={Hash} title="Product links: exact only">
          Page-token lookups have no text to compare, so they can only hit on the exact same token. This fixed a bug where every link returned the first product.
        </Note>
        <Note icon={Sparkles} title="Fails safe">
          Redis down? The cache switches to passthrough: searches still work, they just cost credits. Nothing crashes.
        </Note>
      </div>
    </div>
  );
}

function Note({ icon: Icon, title, children }: { icon: ComponentType<{ className?: string }>; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-bg/40 p-3">
      <div className="mb-1 flex items-center gap-1.5 font-medium text-ink">
        <Icon className="h-3.5 w-3.5 text-faint" /> {title}
      </div>
      {children}
    </div>
  );
}
