import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Production static assets are served by FastAPI at the same origin as /api.
export default function config(phase: string): NextConfig {
  const development = phase === PHASE_DEVELOPMENT_SERVER;
  return {
    distDir: development
      ? (process.env.COLDLINE_NEXT_DIST_DIR ?? ".next")
      : ".next",
    output: development ? undefined : "export",
    trailingSlash: true,
    // FastAPI uses slashless /api routes. Avoid redirect loops before rewrites.
    skipTrailingSlashRedirect: true,
    poweredByHeader: false,
    ...(development && {
      async rewrites() {
        return [
          {
            source: "/api/:path*",
            destination: `${process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000"}/api/:path*`,
          },
        ];
      },
    }),
  };
}
