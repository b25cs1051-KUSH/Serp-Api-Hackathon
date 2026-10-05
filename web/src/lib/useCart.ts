"use client";

import { useSyncExternalStore } from "react";
import type { RxItem } from "./api";

/** The shop's cart: prescription lines ({q, tablets}), kept in this browser. Storage may be blocked: it then lasts for the visit. */
const KEY = "pharmawatch-cart";
export const MAX_LINES = 8;
const EMPTY: RxItem[] = [];

let items: RxItem[] | null = null;
const listeners = new Set<() => void>();

const valid = (x: unknown): x is RxItem =>
  typeof x === "object" && x !== null && typeof (x as RxItem).q === "string" &&
  ((x as RxItem).tablets === null || (Number.isInteger((x as RxItem).tablets) && (x as RxItem).tablets! > 0));

function read(): RxItem[] {
  if (items) return items;
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    items = Array.isArray(parsed) ? parsed.filter(valid).slice(0, MAX_LINES) : [];
  } catch {
    items = [];
  }
  return items;
}

function write(next: RxItem[]) {
  items = next.slice(0, MAX_LINES);
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* storage blocked: kept in memory for this visit */
  }
  listeners.forEach((l) => l());
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

export function useCart() {
  const cart = useSyncExternalStore(subscribe, read, () => EMPTY);
  return {
    items: cart,
    count: cart.filter((it) => it.q.trim()).length,
    full: cart.length >= MAX_LINES,
    /** Adds a medicine, or updates its tablet count if it is already in the cart. */
    add: (q: string, tablets: number | null) => {
      const cur = read();
      const i = cur.findIndex((it) => same(it.q, q));
      if (i >= 0) write(cur.map((it, j) => (j === i ? { ...it, tablets } : it)));
      else if (cur.length < MAX_LINES) write([...cur, { q, tablets }]);
    },
    has: (q: string) => cart.some((it) => same(it.q, q)),
    set: (next: RxItem[]) => write(next),
    clear: () => write([]),
  };
}
