import type { NextConfig } from "next";
import { readFileSync } from "fs";

const pkg = JSON.parse(readFileSync("./package.json", "utf8"));

const nextConfig: NextConfig = {
  env: {
    APP_VERSION: pkg.version,
  },
  output: "standalone",
  transpilePackages: [
    "@docu-store/ui",
    "@docu-store/types",
    "@docu-store/api-client",
    "@sentinel-auth/js",
    "@sentinel-auth/react",
    "@sentinel-auth/nextjs",
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
