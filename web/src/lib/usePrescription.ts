"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, type BasketResult, type Call, type DoneSummary, type RxItem, type RxLine } from "./api";
import { waitForApiReady } from "./apiReady";
import type { SearchState, Stage } from "./useSearch";

export interface PrescriptionState {
  status: "idle" | "running" | "done" | "error";
  waking: boolean;
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
  waking: false,
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
  const pendingRef = useRef<AbortController | null>(null);
  useEffect(() => () => {
    pendingRef.current?.abort();
    esRef.current?.close();
  }, []);

  const run = useCallback(
    async (items: RxItem[], pincode: string, links: boolean) => {
      pendingRef.current?.abort();
      esRef.current?.close();
      const controller = new AbortController();
      pendingRef.current = controller;
      setState({ ...initial, status: "running", waking: true, items, pincode, startedAt: performance.now() });
      try {
        await waitForApiReady({ signal: controller.signal });
      } catch (error) {
        if (!controller.signal.aborted) {
          setState((s) => ({ ...s, status: "error", waking: false, error: (error as Error).message }));
        }
        return;
      }
      if (controller.signal.aborted) return;
      setState((s) => ({ ...s, waking: false }));

      const url = `${API_URL}/api/prescription/stream?items=${encodeURIComponent(JSON.stringify(items))}&pincode=${encodeURIComponent(pincode)}&links=${links}`;
      const es = new EventSource(url);
      esRef.current = es;

      const on = <T,>(name: string, fn: (data: T) => void) =>
        es.addEventListener(name, (e) => {
          if (controller.signal.aborted) return;
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
        if (controller.signal.aborted) return;
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
    waking: s.waking,
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
