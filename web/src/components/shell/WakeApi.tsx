"use client";

import { useEffect } from "react";
import { waitForApiReady } from "@/lib/apiReady";

/** The cover renders immediately; hydration wakes the live API in the background. */
export default function WakeApi() {
  useEffect(() => {
    const controller = new AbortController();
    void waitForApiReady({ signal: controller.signal }).catch(() => {
      // A submitted search handles connection failures in the normal app UI.
    });
    return () => controller.abort();
  }, []);
  return null;
}
