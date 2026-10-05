import type { Metadata } from "next";
import ShopView from "@/components/views/ShopView";

export const metadata: Metadata = { title: "PharmaWatch Shop" };

export default function ShopPage() {
  return <ShopView />;
}
