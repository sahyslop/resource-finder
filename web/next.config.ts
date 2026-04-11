import type { NextConfig } from "next";

/**
 * When NEXT_PUBLIC_API_URL is unset, the browser calls same-origin `/api/*` and
 * Next proxies to Flask — avoids CORS (e.g. app on localhost:3000 vs API on 127.0.0.1:5000).
 * Override upstream with API_UPSTREAM if Flask is not on 127.0.0.1:5000.
 */
const explicitBrowserApi = process.env.NEXT_PUBLIC_API_URL?.trim();
const apiUpstream =
  process.env.API_UPSTREAM?.trim().replace(/\/$/, "") ||
  "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  async rewrites() {
    if (explicitBrowserApi) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${apiUpstream}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
