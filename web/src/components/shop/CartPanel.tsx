"use client";

import { ShoppingCart, X } from "lucide-react";
import { useEffect, useRef } from "react";
import PrescriptionForm from "@/components/PrescriptionForm";
import type { RxItem } from "@/lib/api";

const BLANK: RxItem[] = [{ q: "", tablets: null }];

/**
 * The cart: a side panel on desktop, a bottom sheet on phones. Lines with tablet counts, edit and
 * remove, paste a list, common prescriptions, and "Find the cheapest basket". Esc or the backdrop closes it.
 */
export default function CartPanel({
  open,
  onClose,
  items,
  setItems,
  pincode,
  setPincode,
  running,
  onFind,
}: {
  open: boolean;
  onClose: () => void;
  items: RxItem[];
  setItems: (items: RxItem[]) => void;
  pincode: string;
  setPincode: (p: string) => void;
  running: boolean;
  onFind: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    panel.current?.querySelector<HTMLInputElement>("input")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  const count = items.filter((it) => it.q.trim()).length;

  return (
    <div className="fixed inset-0 z-40">
      <button type="button" aria-label="Close cart" onClick={onClose} className="absolute inset-0 bg-black/30" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-title"
        className="absolute inset-x-0 bottom-0 flex max-h-[88vh] flex-col rounded-t-2xl border-t border-line bg-bg shadow-2xl sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[460px] sm:rounded-none sm:border-l sm:border-t-0"
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 id="cart-title" className="flex items-center gap-2 font-semibold">
            <ShoppingCart className="h-4 w-4" /> Your cart <span className="tnum text-sm font-normal text-muted">({count})</span>
          </h2>
          <button type="button" onClick={onClose} aria-label="Close cart" className="rounded-lg p-2 text-muted hover:bg-panel-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 pb-4">
          <p className="px-1 pt-3 text-sm text-muted">Add medicines from search, paste your prescription (one per line, e.g. &ldquo;Dolo 650 x30&rdquo;), or start from a common one.</p>
          <PrescriptionForm items={items.length ? items : BLANK} setItems={setItems} pincode={pincode} setPincode={setPincode} running={running} onSubmit={onFind} />
        </div>
      </div>
    </div>
  );
}
