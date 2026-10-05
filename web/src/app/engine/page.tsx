import type { Metadata } from "next";
import EngineView from "@/components/views/EngineView";

export const metadata: Metadata = { title: "PharmaWatch: Under the hood" };

export default function EnginePage() {
  return <EngineView />;
}
