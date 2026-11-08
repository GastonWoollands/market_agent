import type { NextConfig } from "next";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Valuation and Opportunities merged into Ideas (Phase 1.16).
  async redirects() {
    return [
      { source: "/valuation", destination: "/ideas", permanent: false },
      { source: "/opportunities", destination: "/ideas", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
