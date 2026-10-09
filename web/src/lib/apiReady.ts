import { API_URL, type Health } from "./api";

/** Wake with free health requests. Search endpoints are never used or retried here. */
export async function waitForApiReady({
  signal,
  timeoutMs = 180_000,
  requestTimeoutMs = 10_000,
  retryMs = 2500,
}: {
  signal: AbortSignal;
  timeoutMs?: number;
  requestTimeoutMs?: number;
  retryMs?: number;
}): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    signal.throwIfAborted();
    const request = new AbortController();
    const abort = () => request.abort();
    signal.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, Math.min(requestTimeoutMs, deadline - Date.now()));
    try {
      const response = await fetch(`${API_URL}/api/health`, {
        cache: "no-store",
        signal: request.signal,
      });
      if (response.ok) {
        const health: Health = await response.json();
        signal.throwIfAborted();
        if (health.model === "ready" && health.serpapi_key_configured) return;
        if (health.model === "failed") break;
      }
    } catch {
      signal.throwIfAborted();
      // Render may return 503, time out, or disconnect while its API starts.
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
    await new Promise<void>((resolve, reject) => {
      const cancel = () => {
        clearTimeout(pause);
        signal.removeEventListener("abort", cancel);
        reject(new DOMException("Cancelled", "AbortError"));
      };
      const pause = setTimeout(() => {
        signal.removeEventListener("abort", cancel);
        resolve();
      }, Math.min(retryMs, Math.max(0, deadline - Date.now())));
      signal.addEventListener("abort", cancel, { once: true });
      if (signal.aborted) cancel();
    });
  }
  signal.throwIfAborted();
  throw new Error("Price comparisons are temporarily unavailable. Please try again.");
}
