"use client";

import { useEffect, useState } from "react";
import { getJSON, type Account } from "@/lib/api";

/** SerpApi quota line: shown only once the API answers (hidden while the free server sleeps). 0 credits. */
function QuotaLine() {
  const [account, setAccount] = useState<Account | null>(null);
  useEffect(() => {
    getJSON<Account>("/api/account").then(setAccount).catch(() => {});
  }, []);
  if (!account) return null;
  return (
    <p className="tnum">
      SerpApi {account.plan_name}: {account.total_searches_left} of {account.searches_per_month} searches left this month (live, costs nothing).
    </p>
  );
}

/** 7. Footer: data sources, the medical caution and the live quota. */
export default function LandingFooter() {
  return (
    <footer className="mt-12 space-y-1.5 border-t border-line pt-6 text-xs text-faint">
      <p>
        Prices: Google Shopping via SerpApi. Medicines and compositions: Indian Medicine Dataset (MIT). Delivery rules per pharmacy and PIN zone,
        from published policies and real checkouts.
      </p>
      <p className="font-medium text-muted">Not medical advice. Ask your doctor or pharmacist before switching brands.</p>
      <QuotaLine />
    </footer>
  );
}
