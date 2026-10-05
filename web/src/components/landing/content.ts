/**
 * Every number on the landing page, with where it comes from. Nothing here is estimated: each value
 * was measured on a real run or read from the repo, and is shown with its date or source.
 */

export const API_DOCS_URL = "https://pharmawatch-api-zmwy.onrender.com/docs";

export const HERO = {
  eyebrow: "SerpApi Google Shopping · Redis semantic cache · 246,046 medicines",
  title: "Your prescription, at the lowest delivered price.",
  sentence:
    "We search Indian e-pharmacies at once, add delivery to your PIN, swap in same-salt generics, and never pay SerpApi twice for the same question.",
};

export type Capability = { title: string; body: string; figure: string; source: string };

export const CAPABILITIES: Capability[] = [
  {
    title: "A repeat search is free",
    body: "The same or a similar question is answered from the Redis cache instead of SerpApi.",
    figure: "0 credits · 1–20 ms",
    source: "Cache hits measured at 1–20 ms, SerpApi calls at 1.7–12 s (README)",
  },
  {
    title: "A different dose is never reused",
    body: "Close wording with different numbers forces a fresh search. A wrong dose is worse than a credit.",
    figure: "Dolo 500 vs Dolo 650 · 0.949 · blocked",
    source: "Cache Lab on the local API, Oct 6, 2026",
  },
  {
    title: "Cheaper than the pharmacy's own pick",
    body: "For Stamlo 5, Chemist180 suggests Amlip 5. We found a same-salt brand that costs less per tablet.",
    figure: "Amodep 5 ₹1.01 vs Amlip 5 ₹1.35 per tablet",
    source: "Reference check, Oct 2, 2026 (scripts/reference_report.md)",
  },
  {
    title: "The price delivered to your PIN",
    body: "Each pharmacy's delivery fee and free-delivery threshold are added before anything is ranked.",
    figure: "14 pharmacies · 5 PIN zones",
    source: "notes/postal_codes_delivery_rules.json",
  },
  {
    title: "Your prescription, optimised as one basket",
    body: "Two medicines in one order can beat buying each where it is cheapest alone. Every split is priced.",
    figure: "8 medicines × 7 pharmacies · 39.6 ms",
    source: "scripts/test_basket.py, Oct 6, 2026",
  },
  {
    title: "Ask from Claude",
    body: "The same search and basket are tools any MCP client can call.",
    figure: "plan_prescription · search_medicine",
    source: "mcp_server.py",
  },
];

export const STEPS: { title: string; body: string }[] = [
  { title: "Recognise the medicine", body: "A local index of 246,046 Indian medicines finds the salt, strength and form, and its other brands. 0 credits." },
  { title: "Search in parallel", body: "Google Shopping via SerpApi, for the medicine and its cheapest same-salt brands, all at once." },
  { title: "Keep only the same composition", body: "Look-alikes such as a different strength or a combination drug are dropped before anything is shown." },
  { title: "Add delivery to your PIN", body: "Each pharmacy's fee and free-delivery threshold for your PIN zone gives the price you actually pay." },
  { title: "Optimise the basket", body: "For a prescription, every way to split it across pharmacies is priced with delivery, and the cheapest wins." },
  { title: "Cache the answer", body: "Results go to Redis. The next similar question costs nothing, unless the dose differs." },
];

/** README "Cheaper than the pharmacies' own suggestions" / scripts/reference_report.md, run on Oct 2, 2026. */
export const BENCHMARK = {
  date: "Oct 2, 2026",
  summary: "10 of 15 medicines at or below the cheapest alternative the pharmacy itself suggests.",
  note:
    "Price per tablet. At the time Chemist180 delivered free; since Oct 3 its ₹100 fee below ₹1,000 is applied in every search.",
  rows: [
    { medicine: "Thyronorm 50", theirs: "Thiroace 50, ₹0.70", ours: "Thyrorich 50 @ Chemist180, ₹0.14", win: true },
    { medicine: "Pan 40", theirs: "Prasopheg 40, ₹2.25", ours: "Pantopraz 40 @ Chemist180, ₹0.66", win: true },
    { medicine: "Stamlo 5", theirs: "Amlip 5, ₹1.35", ours: "Amodep 5 @ Chemist180, ₹1.01", win: true },
    { medicine: "Atorbest 10", theirs: "Lipvas 10, ₹3.30", ours: "Atorless 10 @ Chemist180, ₹2.73", win: true },
    { medicine: "Azithral 500", theirs: "Azikem 500, ₹18.12", ours: "Azivent 500 @ Chemist180, ₹14.78", win: true },
    { medicine: "Dolo 650", theirs: "Paracip 650, ₹1.39", ours: "Paracip 650 @ Chemist180, ₹1.39", win: true },
    { medicine: "Rosuvas 10", theirs: "Rosemicor 10, ₹2.25", ours: "Rosudac 10, ₹2.94 (miss)", win: false },
  ],
};

export const MCP_CONFIG = `{
  "mcpServers": {
    "pharmawatch": {
      "command": "python",
      "args": ["/absolute/path/to/Serp-Api-Hackathon/mcp_server.py"]
    }
  }
}`;
