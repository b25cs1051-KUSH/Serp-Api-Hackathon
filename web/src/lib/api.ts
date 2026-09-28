export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type CallKind = "exact" | "semantic" | "api" | "passthrough";

export interface Call {
  n: number;
  tag: string;
  engine: string;
  query: string;
  kind: CallKind;
  similarity: number | null;
  start_ms: number;
  ms: number;
  credit: boolean;
}

export interface Listing {
  platform: string;
  platform_logo?: string;
  medicine_name: string;
  price_inr: number;
  delivery_fee: number | null;
  platform_fee?: number;
  delivery_label: string;
  delivery_status: "free" | "charged" | "pickup_only" | "unserviceable" | "unknown";
  total_landed_cost: number | null;
  estimated_days?: string;
  direct_link?: string;
  search_link?: string;
  google_link?: string;
  is_cheapest?: boolean;
  rank?: number;
  thumbnail?: string;
  pincode_zone?: string;
  manufacturer?: string;
}

export interface Alternative extends Listing {
  brand: string;
  pack_size: number | null;
  pack_estimated: boolean;
  unit_landed_cost: number | null;
  savings?: number;
  savings_pct?: number;
  price_basis?: "per_tablet" | "total";
  is_cheaper?: boolean;
  estimated?: boolean;
  widely_stocked?: boolean;
}

export interface AltResult {
  query: string;
  composition: { name: string; active_ingredient: string; drug_class: string; brands: string[]; brand_count?: number };
  suggested_alternatives: string[];
  matched_as: "brand" | "salt";
  matched_brand: string | null;
  matched_by: "exact" | "fuzzy" | "gemini";
  match_reason: string;
  reference: Alternative | null;
  cheaper_alternatives: Alternative[];
  other_alternatives: Alternative[];
  not_found: string[];
  timings?: Record<string, number>;
}

/** The search named a salt or brand without its strength: pick one before anything is searched. */
export interface ChooseOptions {
  query: string;
  reason: string;
  options: { label: string; query: string }[];
}

export interface DoneSummary {
  total_ms: number;
  calls: number;
  credits_spent: number;
  credits_saved: number;
  exact_hits: number;
  semantic_hits: number;
  est_time_saved_ms: number;
  timings: Record<string, number>;
}

export interface Health {
  redis_ok: boolean;
  redis: string;
  model: "pending" | "warming" | "ready" | "failed";
  model_warm_ms: number | null;
  similarity_threshold: number;
  serpapi_key_configured: boolean;
  gemini_key_configured: boolean;
  lab_available: boolean;
}

export interface Account {
  plan_name: string;
  searches_per_month: number;
  this_month_usage: number;
  plan_searches_left: number;
  total_searches_left: number;
  last_hour_searches: number;
}

export interface Stats {
  cache: { cache_size: number; backend: string };
  session: {
    searches: number;
    serpapi_calls: number;
    credits_spent: number;
    credits_saved: number;
    exact_hits: number;
    semantic_hits: number;
    hit_rate_pct: number;
    avg_api_ms: number | null;
    avg_hit_ms: number | null;
    time_saved_ms: number;
  };
}

export interface LabResult {
  input: string;
  normalized_query: string;
  cache_key: string;
  threshold: number;
  decision: "exact_hit" | "semantic_hit" | "api_call";
  reason: string;
  credits: number;
  compared_against: number;
  timings_ms: { exact_lookup: number; embed: number; scan: number };
  nearest: { query_text: string; similarity: number; above_threshold: boolean; dosage_guard_blocks: boolean; same_params: boolean }[];
}

export interface CacheEntries {
  redis_ok: boolean;
  entries: { key: string; query_text: string; kind: "shopping" | "product_link" | "llm_decision"; ttl_s: number | null; bytes: number }[];
  counts: Record<string, number>;
  total_bytes?: number;
}

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const inr = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

export const fmtMs = (ms: number | null | undefined) =>
  ms == null ? "—" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : ms >= 10 ? `${Math.round(ms)} ms` : `${ms.toFixed(1)} ms`;

export const fmtTtl = (s: number | null) => {
  if (s == null) return "no expiry";
  if (s >= 86400) return `${Math.round(s / 86400)} d`;
  if (s >= 3600) return `${Math.round(s / 3600)} h`;
  return `${Math.max(1, Math.round(s / 60))} min`;
};

export const fmtBytes = (b: number) =>
  b >= 1_048_576 ? `${(b / 1_048_576).toFixed(1)} MB` : b >= 1024 ? `${Math.round(b / 1024)} KB` : `${b} B`;
