import DemoPanel from "@/components/landing/DemoPanel";
import HeroSaving from "@/components/landing/HeroSaving";
import LandingFooter from "@/components/landing/LandingFooter";
import { Benchmark, Capabilities, ForDevelopers, Hero, HowItWorks } from "@/components/landing/Sections";
import LegacyViewRedirect from "@/components/shell/LegacyViewRedirect";
import SiteHeader from "@/components/shell/SiteHeader";

/** Landing page: static content, so it renders in full even while the API sleeps. */
export default function Home() {
  return (
    <div className="theme-light min-h-screen w-full">
      <main className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-6">
        <LegacyViewRedirect />
        <SiteHeader />
        <Hero aside={<HeroSaving />} />
        <DemoPanel />
        <Capabilities />
        <HowItWorks />
        <Benchmark />
        <ForDevelopers />
        <LandingFooter />
      </main>
    </div>
  );
}
