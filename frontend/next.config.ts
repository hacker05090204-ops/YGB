import type { NextConfig } from "next";

const isProduction = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  outputFileTracingRoot: process.cwd(),
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
  compiler: {
    removeConsole: isProduction,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
