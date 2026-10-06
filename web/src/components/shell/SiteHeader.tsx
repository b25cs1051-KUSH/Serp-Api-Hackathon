import { BookOpen, Cpu } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

export const GITHUB_URL = "https://github.com/b25cs1051-KUSH/Serp-Api-Hackathon";
export const DOCS_URL = `${GITHUB_URL}#readme`;

function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className={className} fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

/** The PharmaWatch mark and name; links to the shop (the home page). */
export function Logo() {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-3 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      <span aria-hidden className="grid h-11 w-11 place-items-center rounded-xl bg-accent text-xl font-black text-white shadow-sm">P</span>
      <span className="flex flex-col leading-tight">
        <span className="text-xl font-bold tracking-tight">PharmaWatch</span>
        <span className="hidden text-xs text-muted sm:block">Medicines at the lowest delivered price</span>
      </span>
    </Link>
  );
}

/** Under the hood, Docs, GitHub: top right on every page. */
export function SiteNav({ current }: { current?: "engine" }) {
  const item = "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-accent";
  return (
    <nav aria-label="Site" className="flex flex-wrap items-center gap-1">
      <Link
        href="/engine"
        aria-current={current === "engine" ? "page" : undefined}
        className={`${item} ${current === "engine" ? "bg-accent text-white" : "border border-line bg-panel text-ink hover:border-accent/60"}`}
      >
        <Cpu aria-hidden className="h-4 w-4" /> Under the hood
      </Link>
      <a href={DOCS_URL} target="_blank" rel="noopener noreferrer" className={`${item} text-muted hover:text-ink`}>
        <BookOpen aria-hidden className="h-4 w-4" /> Docs
      </a>
      <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className={`${item} text-muted hover:text-ink`}>
        <GithubMark className="h-4 w-4" /> GitHub
      </a>
    </nav>
  );
}

/** Logo left, site navigation right; `children` adds a second row (the shop's tabs and PIN). */
export default function SiteHeader({ current, children }: { current?: "engine"; children?: ReactNode }) {
  return (
    <header className="flex flex-col gap-3 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Logo />
        <SiteNav current={current} />
      </div>
      {children}
    </header>
  );
}
