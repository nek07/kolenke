import type { NextConfig } from "next";

// The FastAPI backend listens on localhost only; the page talks to it through this proxy,
// so the browser sees one origin and no CORS is needed.
const API_URL = process.env.KOLENKE_API_URL ?? "http://127.0.0.1:8765";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // end-to-end tests build into their own folder, so they never replace the build you run
  distDir: process.env.KOLENKE_DIST_DIR ?? ".next",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
