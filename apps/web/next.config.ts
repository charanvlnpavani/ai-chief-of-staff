import type { NextConfig } from "next";

// The browser only ever talks to this origin. Requests to /api/* are proxied to FastAPI,
// so the session cookie stays first-party (HttpOnly, SameSite=Lax) and no CORS is needed.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // The /api proxy to FastAPI gives up after 30 s by default, which turned slow but successful
    // AI calls into 500s. Long work (roadmap drafts) now runs as a background job that the page
    // polls; this headroom covers single AI calls such as a slow local model answering.
    proxyTimeout: 120_000,
  },
  poweredByHeader: false,
  transpilePackages: ["@personal-os/api-client"],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
