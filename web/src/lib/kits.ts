import type { RxItem } from "./api";

/**
 * Common prescriptions by condition. Examples to start from, never advice: a click fills the form
 * (nothing is searched) and the user edits it to match what their doctor prescribed.
 */
/** Chip colours on the shop: [idle, selected] classes, one hue per condition. */
export const KIT_COLORS: Record<string, [string, string]> = {
  diabetes: ["border-sky-300 bg-sky-50 text-sky-800", "border-sky-600 bg-sky-600 text-white"],
  bp: ["border-rose-300 bg-rose-50 text-rose-800", "border-rose-600 bg-rose-600 text-white"],
  cold: ["border-amber-300 bg-amber-50 text-amber-900", "border-amber-500 bg-amber-500 text-white"],
  acidity: ["border-violet-300 bg-violet-50 text-violet-800", "border-violet-600 bg-violet-600 text-white"],
  cholesterol: ["border-emerald-300 bg-emerald-50 text-emerald-800", "border-emerald-600 bg-emerald-600 text-white"],
  thyroid: ["border-teal-300 bg-teal-50 text-teal-800", "border-teal-600 bg-teal-600 text-white"],
};

export const KITS: { id: string; label: string; items: RxItem[] }[] = [
  { id: "diabetes", label: "Diabetes", items: [{ q: "Glycomet GP 2", tablets: 30 }, { q: "Rosuvas 10", tablets: 30 }] },
  { id: "bp", label: "High blood pressure", items: [{ q: "Telma 40", tablets: 30 }, { q: "Stamlo 5", tablets: 30 }] },
  {
    id: "cold",
    label: "Cold, cough & fever",
    items: [{ q: "Dolo 650", tablets: 15 }, { q: "Montair LC", tablets: 10 }, { q: "Mucolite", tablets: 10 }],
  },
  { id: "acidity", label: "Acidity", items: [{ q: "Pan 40", tablets: 15 }] },
  { id: "cholesterol", label: "Cholesterol", items: [{ q: "Atorbest 10", tablets: 30 }] },
  { id: "thyroid", label: "Thyroid", items: [{ q: "Thyronorm 50mcg", tablets: 30 }] },
];

/** The kit whose medicines the rows still hold unchanged, if any. */
export const matchingKit = (items: RxItem[]) =>
  KITS.find(
    (k) => k.items.length === items.length && k.items.every((it, i) => it.q === items[i].q && it.tablets === items[i].tablets),
  );
