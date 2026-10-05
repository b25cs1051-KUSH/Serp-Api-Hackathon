import type { BasketResult, Call, DoneSummary, RxItem } from "@/lib/api";
import recorded from "@/data/demo-prescription.json";

/** A real prescription run recorded from the local API (scripts: see README), shown while the API sleeps. */
export interface DemoRun {
  recorded_at: string;
  source: string;
  pincode: string;
  items: RxItem[];
  calls: Call[];
  summary: DoneSummary;
  basket: BasketResult;
  dosage_guard: { input: string; nearest: string; similarity: number; decision: string; reason: string };
}

export const DEMO = recorded as unknown as DemoRun;

export const recordedLabel = (d: DemoRun) =>
  `Recorded from a real run on ${new Date(`${d.recorded_at}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`;
