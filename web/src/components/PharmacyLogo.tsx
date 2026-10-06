"use client";

import { useState } from "react";
import { logoSources } from "@/lib/logos";

const SIZE = { sm: "h-5 w-5 text-[10px]", md: "h-7 w-7 text-xs", lg: "h-9 w-9 text-sm" } as const;

/** A pharmacy's logo: its store icon, else its site icon, else its initial. Decorative: the name is always shown next to it. */
export default function PharmacyLogo({ platform, src, size = "md" }: { platform: string; src?: string; size?: keyof typeof SIZE }) {
  const sources = logoSources(platform, src);
  const [failed, setFailed] = useState(0);
  const url = sources[failed];
  const box = `${SIZE[size]} shrink-0 rounded-md border border-line bg-white`;
  if (!url) {
    return (
      <span aria-hidden className={`${box} grid place-items-center font-semibold text-muted`}>
        {platform.trim().charAt(0).toUpperCase() || "?"}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- third-party store icons, any host
    <img key={url} src={url} alt="" aria-hidden onError={() => setFailed((n) => n + 1)} className={`${box} object-contain p-0.5`} />
  );
}
