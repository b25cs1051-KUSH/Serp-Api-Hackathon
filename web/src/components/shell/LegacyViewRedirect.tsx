"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Old links used /?view=engine; send them to /engine. Client-side, so the site stays static-exportable. */
export default function LegacyViewRedirect() {
  const router = useRouter();
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("view") === "engine") router.replace("/engine");
  }, [router]);
  return null;
}
