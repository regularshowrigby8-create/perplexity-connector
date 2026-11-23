import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["*.e2b.app", "*.arena.ai", "localhost", "127.0.0.1"],
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  experimental: { proxyTimeout: 300_000 },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [{ key: "X-Content-Type-Options", value: "nosniff" }],
    }];
  },
};

export default nextConfig;
