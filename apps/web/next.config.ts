import type { NextConfig } from "next";

const internalApiUrl = process.env.WEB_INTERNAL_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiUrl}/api/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${internalApiUrl}/auth/:path*`,
      },
      {
        source: "/health/:path*",
        destination: `${internalApiUrl}/health/:path*`,
      },
    ];
  },
};

export default nextConfig;
