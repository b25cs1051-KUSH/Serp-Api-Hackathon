import type { RxItem } from "./api";

/**
 * Common prescriptions by condition. Examples to start from, never advice: a click fills the form
 * (nothing is searched) and the user edits it to match what their doctor prescribed.
 */
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
