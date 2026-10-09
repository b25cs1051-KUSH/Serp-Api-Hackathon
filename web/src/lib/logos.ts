/**
 * Pharmacy logos. Search results carry each store's icon (platform_logo, from Google Shopping); basket
 * offers and some alternatives don't. The first icon seen for a pharmacy is remembered and reused for it
 * everywhere; before one is seen, the pharmacy's site icon is used, then its initial.
 */

/** Sites of the pharmacies PharmaWatch prices (each platform's listing.domain in notes/postal_codes_delivery_rules.json). */
const DOMAINS: Record<string, string> = {
  "1mg": "1mg.com",
  PharmEasy: "pharmeasy.in",
  Netmeds: "netmeds.com",
  Truemeds: "truemeds.in",
  "Apollo Pharmacy": "apollopharmacy.in",
  Medplus: "medplusmart.com",
  "Dawaa Dost": "dawaadost.com",
  Chemist180: "chemist180.com",
  Medizinhub: "medizinhub.com",
  SastaSundar: "sastasundar.com",
};

const seen = new Map<string, string>();

/** Remember the store icons in a batch of rows (listings or alternatives). */
export function rememberLogos(rows: { platform?: string; platform_logo?: string }[] | null | undefined) {
  for (const r of rows ?? []) {
    if (r.platform && r.platform_logo && !seen.has(r.platform)) seen.set(r.platform, r.platform_logo);
  }
}

/** Candidate image URLs for a pharmacy, best first. */
export function logoSources(platform: string, own?: string): string[] {
  const out: string[] = [];
  for (const src of [own, seen.get(platform)]) if (src && !out.includes(src)) out.push(src);
  const domain = DOMAINS[platform];
  if (domain) out.push(`https://www.google.com/s2/favicons?domain=${domain}&sz=64`);
  return out;
}
