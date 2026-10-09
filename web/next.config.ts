import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Render Static Sites export HTML; Docker keeps its standalone server.
  output: process.env.NEXT_OUTPUT === "export" ? "export" : "standalone",
};

export default nextConfig;
