"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** /shop (and /shop?tab=rx) moved to / ; client-side, so the site stays static-exportable. */
export default function ShopRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace(`/${window.location.search}`);
  }, [router]);
  return null;
}
