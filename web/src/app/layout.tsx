import type { Metadata } from "next";
import { IBM_Plex_Mono, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

const sans = Schibsted_Grotesk({ variable: "--font-ui", subsets: ["latin"] });
const mono = IBM_Plex_Mono({ variable: "--font-code", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "PharmaWatch",
  description:
    "Cheapest price across Indian e-pharmacies including delivery to your PIN, verified generic substitutes, and a Redis semantic cache that makes repeat searches free.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
