"use client";

import { useCallback, useRef, useState } from "react";
import { API_URL, type BasketResult, type Call, type DoneSummary, type RxItem, type RxLine } from "./api";
import type { SearchState, Stage } from "./useSearch";

export interface PrescriptionState {
  status: "idle" | "running" | "done" | "error";
  items: RxItem[];
  pincode: string;
  lines: Record<number, RxLine>;
  basket: BasketResult | null;
  linksResolved: boolean;
  calls: Call[];
  stages: Stage[];
  done: DoneSummary | null;
  error: string | null;
  startedAt: number;
}

const initial: PrescriptionState = {
  status: "idle",
  items: [],
  pincode: "",
  lines: {},
  basket: null,
  linksResolved: false,
  calls: [],
  stages: [],
  done: null,
  error: null,
  startedAt: 0,
};

/** A whole prescription streamed over SSE. Closed on done/error so EventSource never retries (a retry spends credits). */
export function usePrescription(onFinished?: () => void) {
  const [state, setState] = useState<PrescriptionState>(initial);
  const esRef = useRef<EventSource | null>(null);

  const run = useCallback(
    (items: RxItem[], pincode: string, links: boolean) => {
      esRef.current?.close();
      setState({ ...initial, status: "running", items, pincode, startedAt: performance.now() });

      const url = `${API_URL}/api/prescription/stream?items=${encodeURIComponent(JSON.stringify(items))}&pincode=${encodeURIComponent(pincode)}&links=${links}`;
      const es = new EventSource(url);
      esRef.current = es;

      const on = <T,>(name: string, fn: (data: T) => void) =>
        es.addEventListener(name, (e) => {
          const data = (e as MessageEvent).data;
          if (typeof data === "string") fn(JSON.parse(data));
        });

      on<Call>("call", (call) => setState((s) => ({ ...s, calls: [...s.calls, call] })));
      on<RxLine & { at_ms: number }>("line", (d) =>
        setState((s) => ({ ...s, lines: { ...s.lines, [d.line]: { ...s.lines[d.line], ...d } } })),
      );
      for (const name of ["basket", "basket_links"] as const) {
        on<{ at_ms: number; result: BasketResult }>(name, (d) =>
          setState((s) => ({
            ...s,
            basket: d.result,
            linksResolved: s.linksResolved || name === "basket_links" || !links,
            stages: [...s.stages, { name, at_ms: d.at_ms }],
          })),
        );
      }
      on<DoneSummary>("done", (d) => {
        es.close();
        setState((s) => ({ ...s, status: s.status === "error" ? "error" : "done", done: d, linksResolved: true }));
        onFinished?.();
      });
      on<{ message: string }>("error", (d) => setState((s) => ({ ...s, status: "error", error: d.message })));

      let opened = false;
      es.onopen = () => {
        opened = true;
      };
      es.onerror = () => {
        if (es.readyState !== EventSource.CLOSED) es.close();
        setState((s) =>
          s.status === "running"
            ? { ...s, status: "error", error: s.error ?? (opened ? "The search stopped before it finished. Try again." : "Can't reach the API.") }
            : s,
        );
      };
    },
    [onFinished],
  );

  return { state, run };
}

/** The prescription run in the shape UnderTheHood reads. */
export function asSearchState(s: PrescriptionState): SearchState {
  return {
    status: s.status,
    query: `${s.items.length} medicines`,
    pincode: s.pincode,
    links: false,
    calls: s.calls,
    stages: s.stages,
    listings: null,
    linksResolved: s.linksResolved,
    alternatives: undefined,
    choose: null,
    done: s.done,
    error: s.error,
    startedAt: s.startedAt,
  };
}
