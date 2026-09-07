/** @type {import('next').NextConfig} */

// Hugging Face Spaces exposes exactly one port, so the Next.js server proxies
// /api/* through to FastAPI running in the same container. Set INTERNAL_API_URL
// to enable it. Left unset (docker compose, local dev) the browser talks to the
// API directly via NEXT_PUBLIC_API_BASE_URL and no rewrite is registered.
const internalApi = process.env.INTERNAL_API_URL;

const nextConfig = {
  output: "standalone",
  async rewrites() {
    if (!internalApi) return [];
    return [{ source: "/api/:path*", destination: `${internalApi}/api/:path*` }];
  },
};

module.exports = nextConfig;
