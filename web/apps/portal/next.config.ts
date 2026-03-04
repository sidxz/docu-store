import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: [
    "@docu-store/ui",
    "@docu-store/types",
    "@docu-store/api-client",
  ],
};

export default nextConfig;
