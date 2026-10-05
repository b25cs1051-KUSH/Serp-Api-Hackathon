"use client";

import { useCallback, useEffect, useState } from "react";
import { getJSON, type Account, type CacheEntries, type Health, type Stats } from "./api";

/**
 * API status for the engine view: /api/health polled until the embedding model is ready (every 3 s
 * while the API is unreachable), plus session stats, cache entries and the SerpApi quota, which
 * refresh() reloads (after every search). All of these endpoints cost 0 credits.
 */
export function useApiStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [entries, setEntries] = useState<CacheEntries | null>(null);

  const refresh = useCallback(() => {
    getJSON<Stats>("/api/stats").then(setStats).catch(() => {});
    getJSON<CacheEntries>("/api/cache/entries").then(setEntries).catch(() => {});
    getJSON<Account>("/api/account").then(setAccount).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    const poll = () =>
      getJSON<Health>("/api/health")
        .then((h) => {
          setHealth(h);
          setHealthErr(false);
          if (!stop && h.model !== "ready") setTimeout(poll, 2000);
        })
        .catch(() => {
          setHealthErr(true);
          if (!stop) setTimeout(poll, 3000);
        });
    poll();
    refresh();
    return () => {
      stop = true;
    };
  }, [refresh]);

  return { health, healthErr, account, stats, entries, refresh };
}
