import type { NextConfig } from "next";
import { readFileSync } from "fs";

const pkg = JSON.parse(readFileSync("./package.json", "utf8"));

const nextConfig: NextConfig = {
  basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "",
  env: {
    APP_VERSION: pkg.version,
  },
  output: "standalone",
  // Baseline security headers. HSTS is the reverse proxy's job. A full CSP
  // needs nonces for Next's inline scripts, so only frame-ancestors is set.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        ],
      },
    ];
  },
  transpilePackages: [
    "@docu-store/ui",
    "@docu-store/types",
    "@docu-store/api-client",
    "@duar-auth/js",
    "@duar-auth/react",
    "ketcher-react",
    "ketcher-core",
    "ketcher-standalone",
  ],

  // @rdkit/rdkit WASM loader conditionally requires "fs" for Node.js;
  // Turbopack can't resolve it in client bundles — alias to empty module.
  turbopack: {
    resolveAlias: {
      fs: { browser: "./src/stubs/node-builtins.ts" },
    },
  },

  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve = config.resolve ?? {};
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
      };
    }
    return config;
  },
};

export default nextConfig;
