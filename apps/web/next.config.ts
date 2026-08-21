import type { NextConfig } from "next";

const apiProxyTarget =
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
      {
        source: "/healthz",
        destination: `${apiProxyTarget}/healthz`,
      },
      {
        source: "/readyz",
        destination: `${apiProxyTarget}/readyz`,
      },
    ];
  },
};

export default nextConfig;
