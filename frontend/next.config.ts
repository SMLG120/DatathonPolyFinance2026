import path from "node:path";
import type { NextConfig } from "next";

/**
 * Static export only. Nothing here may depend on a Node.js server:
 * no API routes, no server actions, no dynamic rendering, no image optimizer.
 * `next build` writes the deployable site to `out/`.
 */
const nextConfig: NextConfig = {
  output: "export",
  // `/` -> `out/index.html`; keeps URLs stable on any static host (Amplify, S3).
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // `next dev` would otherwise write an AGENTS.md into this folder. The pointer
  // it contains (version-matched docs in node_modules/next/dist/docs) is
  // recorded in README.md instead.
  agentRules: false,
  // Pin the workspace root to this folder so a lockfile elsewhere on the
  // machine cannot change how the app is resolved or built.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
