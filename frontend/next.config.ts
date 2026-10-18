import type { NextConfig } from "next";

const apiHostname = new URL(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
).hostname;

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    ...new Set([
      "localhost",
      "127.0.0.1",
      "10.54.15.175",
      "0.0.0.0",
      apiHostname,
    ]),
  ],
};

export default nextConfig;
