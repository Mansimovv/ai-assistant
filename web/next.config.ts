import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Small self-contained server for the Docker image.
  output: "standalone",
  /* config options here */
};

export default nextConfig;
