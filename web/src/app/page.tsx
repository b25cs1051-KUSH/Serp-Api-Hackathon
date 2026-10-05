import Link from "next/link";
import LegacyViewRedirect from "@/components/shell/LegacyViewRedirect";
import SiteFooter from "@/components/shell/SiteFooter";
import SiteHeader from "@/components/shell/SiteHeader";

/** Landing page. Placeholder until U2: the two ways in. */
export default function Home() {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 pb-24 sm:px-6">
      <LegacyViewRedirect />
      <SiteHeader />
      <section className="pt-12 pb-8">
        <h1 className="max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">Your prescription, at the lowest delivered price.</h1>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/shop" className="rounded-lg bg-hit px-5 py-3 text-sm font-semibold text-bg hover:brightness-110">
            Try a prescription
          </Link>
          <Link href="/engine" className="rounded-lg border border-line px-5 py-3 text-sm font-medium text-ink hover:border-hit/50">
            See under the hood
          </Link>
        </div>
      </section>
      <SiteFooter />
    </main>
  );
}
