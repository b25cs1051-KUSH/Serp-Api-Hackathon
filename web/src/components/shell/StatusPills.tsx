"use client";

import { Pill } from "@/components/ui";
import { fmtMs, type Account, type Health } from "@/lib/api";

/** Redis, embedding model, SerpApi credits left and Gemini, from /api/health and /api/account (0 credits). */
export default function StatusPills({ health, healthErr, account }: { health: Health | null; healthErr: boolean; account: Account | null }) {
  return (
    <div className="-mt-1 flex flex-wrap justify-end gap-2">
      {healthErr ? (
        <Pill ok={false}>API offline: start uvicorn on :8000</Pill>
      ) : (
        <>
          <Pill ok={health ? health.redis_ok : null} title={health?.redis}>
            Redis {health ? (health.redis_ok ? "connected" : "down: passthrough") : "…"}
          </Pill>
          <Pill ok={health ? (health.model === "ready" ? true : health.model === "failed" ? false : null) : null}>
            Embedding model {health?.model === "ready" ? `warm${health.model_warm_ms ? ` (${fmtMs(health.model_warm_ms)} at boot)` : ""}` : health?.model ?? "…"}
          </Pill>
          <Pill ok={account ? account.total_searches_left > 20 : null} title="Live from SerpApi account.json (free)">
            SerpApi {account ? `${account.total_searches_left} / ${account.searches_per_month} credits left` : "…"}
          </Pill>
          <Pill ok={health ? health.gemini_key_configured : null}>Gemini {health?.gemini_key_configured ? "on" : "off"}</Pill>
        </>
      )}
    </div>
  );
}
