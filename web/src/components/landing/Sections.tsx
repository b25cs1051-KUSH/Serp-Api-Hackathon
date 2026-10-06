import { ArrowRight, Check, Minus } from "lucide-react";
import Link from "next/link";
import { GITHUB_URL } from "@/components/shell/SiteHeader";
import { API_DOCS_URL, BENCHMARK, CAPABILITIES, HERO, MCP_CONFIG, STEPS } from "./content";
import { DEMO } from "./demo";

/** /engine with the recorded prescription preloaded: it runs from the cache, with product links off. */
export const ENGINE_DEMO_HREF = `/engine?${new URLSearchParams({
  rx: DEMO.items.map((it) => (it.tablets ? `${it.q} x${it.tablets}` : it.q)).join(";"),
  pin: DEMO.pincode,
})}`;

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-hit">{children}</div>;
}

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mb-6 max-w-2xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
      {sub && <p className="mt-2 text-sm text-muted">{sub}</p>}
    </div>
  );
}

/** 1. Hero. `aside` is the recorded-run saving (U3); nothing is shown there until it exists. */
export function Hero({ aside }: { aside?: React.ReactNode }) {
  return (
    <section className="grid gap-8 pt-10 pb-12 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:items-end">
      <div className="min-w-0">
        <p className="text-xs text-muted">{HERO.eyebrow}</p>
        <h1 className="mt-4 text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl">{HERO.title}</h1>
        <p className="mt-5 max-w-xl text-base text-muted">{HERO.sentence}</p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link
            href="/shop"
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Try a prescription <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href={ENGINE_DEMO_HREF}
            className="inline-flex items-center rounded-lg border border-line bg-panel px-5 py-3 text-sm font-medium text-ink hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            See under the hood
          </Link>
        </div>
      </div>
      {aside && <div className="min-w-0">{aside}</div>}
    </section>
  );
}

/** 3. Capability cards: a claim and one measured number each. */
export function Capabilities() {
  return (
    <section className="py-12">
      <SectionHead eyebrow="What it does" title="Every claim comes with a measured number" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {CAPABILITIES.map((c) => (
          <div key={c.title} className="flex flex-col rounded-xl border border-line bg-panel p-5">
            <h3 className="font-semibold">{c.title}</h3>
            <p className="mt-1.5 text-sm text-muted">{c.body}</p>
            <div className="flex-1" />
            <div className="tnum mt-4 font-mono text-sm font-medium text-ink">{c.figure}</div>
            <div className="mt-1 text-[11px] text-faint">{c.source}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** 4. How it works: the real order of a search. */
export function HowItWorks() {
  return (
    <section className="py-12">
      <SectionHead eyebrow="How it works" title="From a name on a prescription to the cheapest basket" />
      <ol className="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            <span className="tnum grid h-7 w-7 shrink-0 place-items-center rounded-full border border-line bg-panel font-mono text-xs text-ink">{i + 1}</span>
            <div>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="mt-1 text-sm text-muted">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** 5. Benchmark against the pharmacies' own "cheaper alternative". */
export function Benchmark() {
  return (
    <section className="py-12">
      <SectionHead eyebrow="Benchmark" title="Cheaper than the pharmacies' own suggestions" sub={BENCHMARK.summary} />
      <div className="overflow-hidden rounded-xl border border-line bg-panel">
        <table className="w-full table-fixed text-sm">
          <thead>
            <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
              <th className="w-[28%] px-4 py-2.5 font-medium">Medicine</th>
              <th className="px-4 py-2.5 font-medium">Pharmacy suggests</th>
              <th className="px-4 py-2.5 font-medium">PharmaWatch finds</th>
            </tr>
          </thead>
          <tbody>
            {BENCHMARK.rows.map((r) => (
              <tr key={r.medicine} className="border-b border-line/70 last:border-0 align-top">
                <td className="px-4 py-2.5 font-medium">{r.medicine}</td>
                <td className="tnum px-4 py-2.5 font-mono text-xs text-muted sm:text-sm">{r.theirs}</td>
                <td className={`tnum px-4 py-2.5 font-mono text-xs sm:text-sm ${r.win ? "text-hit" : "text-muted"}`}>
                  <span className="inline-flex items-start gap-1.5">
                    {r.win ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <Minus className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
                    {r.ours}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-faint">
        Recorded from a real run on {BENCHMARK.date}. {BENCHMARK.note}
      </p>
    </section>
  );
}

/** 6. For developers. */
export function ForDevelopers() {
  return (
    <section className="py-12">
      <SectionHead eyebrow="For developers" title="Use it from Claude, the API or your own machine" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="min-w-0 rounded-xl border border-line bg-panel p-5">
          <h3 className="font-semibold">Claude Desktop (MCP)</h3>
          <p className="mt-1 text-sm text-muted">
            Add to <code className="font-mono text-xs">claude_desktop_config.json</code>, then ask &ldquo;Where is Stamlo 5 cheapest delivered to 110001?&rdquo;
          </p>
          <pre tabIndex={0} aria-label="claude_desktop_config.json" className="theme-console mt-3 overflow-x-auto rounded-lg p-4 font-mono text-xs leading-relaxed focus-visible:outline-2 focus-visible:outline-hit">{MCP_CONFIG}</pre>
        </div>
        <div className="min-w-0 space-y-4">
          <div className="rounded-xl border border-line bg-panel p-5">
            <h3 className="font-semibold">Run it locally</h3>
            <pre tabIndex={0} aria-label="Command" className="theme-console mt-3 overflow-x-auto rounded-lg p-4 font-mono text-xs focus-visible:outline-2 focus-visible:outline-hit">docker compose up --build</pre>
            <p className="mt-2 text-xs text-muted">UI on :3000, API on :8000, Redis on :6379. Needs a SerpApi key in .env.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href={API_DOCS_URL} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-line bg-panel px-4 py-2 text-sm hover:border-accent/50">
              API docs
            </a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-line bg-panel px-4 py-2 text-sm hover:border-accent/50">
              GitHub
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
