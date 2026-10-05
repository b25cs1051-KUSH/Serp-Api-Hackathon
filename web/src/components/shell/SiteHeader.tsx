import Link from "next/link";

export const GITHUB_URL = "https://github.com/b25cs1051-KUSH/Serp-Api-Hackathon";
export const DOCS_URL = `${GITHUB_URL}#readme`;

/** Logo (links home) and, on the landing page and the engine, the site navigation. The shop shows the logo only. */
export default function SiteHeader({ nav = true, tagline }: { nav?: boolean; tagline?: string }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 py-5">
      <Link href="/" className="flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-hit">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-hit to-sem text-sm font-black text-bg">P</div>
        <div>
          <div className="font-semibold leading-tight">PharmaWatch</div>
          {tagline && <div className="text-[11px] text-faint">{tagline}</div>}
        </div>
      </Link>
      {nav && (
        <nav aria-label="Site" className="flex flex-wrap items-center gap-1 text-sm">
          <Link href="/shop" className="rounded-lg px-3 py-1.5 font-medium text-muted hover:text-ink">Try a prescription</Link>
          <Link href="/engine" className="rounded-lg px-3 py-1.5 font-medium text-muted hover:text-ink">Under the hood</Link>
          <a href={DOCS_URL} target="_blank" rel="noopener noreferrer" className="rounded-lg px-3 py-1.5 text-muted hover:text-ink">Docs</a>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="rounded-lg px-3 py-1.5 text-muted hover:text-ink">GitHub</a>
        </nav>
      )}
    </header>
  );
}
