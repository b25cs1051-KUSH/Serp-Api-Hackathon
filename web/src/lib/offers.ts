import type { Alternative, AltResult, Listing } from "./api";

/**
 * One row of an offer list: a listing of the searched medicine, or the best listing of a same-salt brand.
 * per_tablet is the delivered cost of one tablet when the pack size is known (stated, or estimated "~").
 */
export interface Offer {
  key: string;
  listing: Listing;
  brand: string;
  isSwap: boolean;
  perTablet: number | null;
  perTabletEstimated: boolean;
  savingsPct: number | null;
}

/**
 * Tablets in a pack, when the title states it: "Strip Of 30 Tablets", "15's", "(30 Tab)", "30 Tablets".
 * Numbers that are part of the medicine's own name or strength ("Telma 40", "Dolo 650") are never a pack size.
 */
export function packFromTitle(title: string, brand: string): number | null {
  const own = new Set(brand.match(/\d+(?:\.\d+)?/g) ?? []);
  const patterns = [/strip\s+of\s+(\d{1,3})/i, /\b(\d{1,3})\s*['’]s\b/i, /\(\s*(\d{1,3})\s*(?:tabs?|tablets?|caps?|capsules?)\s*\)/i, /\b(\d{1,3})\s+(?:tablets|capsules)\b/i];
  for (const re of patterns) {
    const m = title.match(re);
    if (m && !own.has(m[1])) {
      const n = Number(m[1]);
      if (n >= 2 && n <= 300) return n;
    }
  }
  return null;
}

const listingKey = (l: Listing, i: number) => `${l.platform}|${l.medicine_name}|${l.price_inr}|${i}`;

/**
 * Every offer for a search: the searched medicine at each pharmacy, then the best offer of each same-salt
 * brand (marked as a swap). The searched brand's pack size from the reference fills in titles that don't state it.
 */
export function buildOffers(brand: string, listings: Listing[], alts: AltResult | null | undefined): Offer[] {
  const refPack = alts?.reference?.pack_size ?? null;
  const own: Offer[] = listings.map((l, i) => {
    const stated = packFromTitle(l.medicine_name, brand);
    const pack = stated ?? refPack;
    return {
      key: listingKey(l, i),
      listing: l,
      brand,
      isSwap: false,
      perTablet: pack && l.total_landed_cost != null ? Math.round((l.total_landed_cost / pack) * 100) / 100 : null,
      perTabletEstimated: stated == null,
      savingsPct: null,
    };
  });
  const swaps: Offer[] = alts
    ? [...alts.cheaper_alternatives, ...alts.other_alternatives].map((a: Alternative, i) => ({
        key: `swap|${a.brand}|${a.platform}|${i}`,
        listing: a,
        brand: a.brand,
        isSwap: true,
        perTablet: a.unit_landed_cost,
        perTabletEstimated: a.pack_estimated,
        savingsPct: a.is_cheaper && a.savings_pct != null ? a.savings_pct : null,
      }))
    : [];
  return [...own, ...swaps];
}

export const deliverable = (o: Offer) => o.listing.delivery_status === "free" || o.listing.delivery_status === "charged";

/** Hours until delivery, from labels like "10-30 Mins / 1 Day", "Same Day / Store Pickup", "1-2 Days". */
export function deliveryHours(days?: string): number {
  if (!days) return 1e6;
  const mins = days.match(/(\d+)(?:\s*-\s*\d+)?\s*min/i);
  if (mins) return Number(mins[1]) / 60;
  if (/same day/i.test(days)) return 8;
  const d = days.match(/(\d+)(?:\s*-\s*\d+)?\s*day/i);
  return d ? Number(d[1]) * 24 : 1e6;
}

/** Deliverable first; then by price per tablet (offers without a known pack size after, by delivered price). */
export function byPrice(a: Offer, b: Offer): number {
  const d = Number(deliverable(b)) - Number(deliverable(a));
  if (d) return d;
  if (a.perTablet != null && b.perTablet != null) return a.perTablet - b.perTablet;
  if (a.perTablet != null) return -1;
  if (b.perTablet != null) return 1;
  return (a.listing.total_landed_cost ?? Infinity) - (b.listing.total_landed_cost ?? Infinity);
}

/** Deliverable first; then soonest, then cheapest per tablet. */
export function bySpeed(a: Offer, b: Offer): number {
  const d = Number(deliverable(b)) - Number(deliverable(a));
  if (d) return d;
  return deliveryHours(a.listing.estimated_days) - deliveryHours(b.listing.estimated_days) || byPrice(a, b);
}
