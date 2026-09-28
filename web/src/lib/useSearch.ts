"use client";

import { useCallback, useRef, useState } from "react";
import { API_URL, type AltResult, type ChooseOptions, type Call, type DoneSummary, type Listing } from "./api";

export type Stage = { name: string; at_ms: number };

export interface SearchState {
  status: "idle" | "running" | "done" | "error";
  query: string;
  pincode: string;
  links: boolean;
  calls: Call[];
  stages: Stage[];
  listings: Listing[] | null;
  linksResolved: boolean;
  alternatives: AltResult | null | undefined; // undefined = not arrived yet, null = not in the medicine index
  choose: ChooseOptions | null; // set when the search needs a strength first; nothing else follows
  done: DoneSummary | null;
  error: string | null;
  startedAt: number;
}

const initial: SearchState = {
  status: "idle",
  query: "",
  pincode: "",
  links: true,
  calls: [],
  stages: [],
  listings: null,
  linksResolved: false,
  alternatives: undefined,
  choose: null,
  done: null,
  error: null,
  startedAt: 0,
};

/** One medicine search streamed over SSE. EventSource is closed on done/error so it never auto-retries (a retry would spend credits). */
export function useSearch(onFinished?: () => void) {
  const [state, setState] = useState<SearchState>(initial);
  const esRef = useRef<EventSource | null>(null);

  const run = useCallback(
    (query: string, pincode: string, links: boolean) => {
      esRef.current?.close();
      setState({ ...initial, status: "running", query, pincode, links, startedAt: performance.now() });

      const url = `${API_URL}/api/search/stream?q=${encodeURIComponent(query)}&pincode=${encodeURIComponent(pincode)}&links=${links}`;
      const es = new EventSource(url);
      esRef.current = es;

      const on = <T,>(name: string, fn: (data: T) => void) =>
        es.addEventListener(name, (e) => {
          const data = (e as MessageEvent).data; // the built-in "error" event (network) has no data
          if (typeof data === "string") fn(JSON.parse(data));
        });

      on<Call>("call", (call) => setState((s) => ({ ...s, calls: [...s.calls, call] })));

      for (const name of ["main", "main_update", "main_links"] as const) {
        on<{ at_ms: number; listings: Listing[] }>(name, (d) =>
          setState((s) => ({
            ...s,
            listings: d.listings,
            linksResolved: s.linksResolved || name === "main_links" || !s.links,
            stages: [...s.stages, { name, at_ms: d.at_ms }],
          })),
        );
      }

      on<ChooseOptions & { at_ms: number }>("choose", (d) =>
        setState((s) => ({ ...s, choose: { query: d.query, reason: d.reason, options: d.options }, stages: [...s.stages, { name: "choose", at_ms: d.at_ms }] })),
      );

      on<{ at_ms: number; result: AltResult | null }>("alternatives", (d) =>
        setState((s) => ({ ...s, alternatives: d.result, stages: [...s.stages, { name: "alternatives", at_ms: d.at_ms }] })),
      );

      on<DoneSummary>("done", (d) => {
        es.close();
        setState((s) => ({ ...s, status: s.status === "error" ? "error" : "done", done: d, linksResolved: true }));
        onFinished?.();
      });

      on<{ message: string }>("error", (d) => {
        setState((s) => ({ ...s, status: "error", error: d.message }));
      });

      let opened = false;
      es.onopen = () => {
        opened = true;
      };

      es.onerror = () => {
        // Network error, rejected request (422/429) or server closed early. Never let EventSource
        // reconnect: a reconnect re-runs the search and can spend credits.
        if (es.readyState !== EventSource.CLOSED) es.close();
        const fail = (message: string) =>
          setState((s) => (s.status === "running" ? { ...s, status: "error", error: s.error ?? message } : s));
        if (opened) {
          fail("The search stopped before it finished. Try again.");
          return;
        }
        // EventSource can't read the status code; a free health check tells "offline" from "rejected".
        fetch(`${API_URL}/api/health`, { cache: "no-store" })
          .then((r) =>
            fail(
              r.ok
                ? "The API refused this search: check the medicine name and 6-digit PIN, or wait a moment if several searches are running."
                : "The API is not healthy right now.",
            ),
          )
          .catch(() => fail("Can't reach the API. Is it running on :8000?"));
      };
    },
    [onFinished],
  );

  return { state, run };
}
