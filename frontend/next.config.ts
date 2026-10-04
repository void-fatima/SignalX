import type { NextConfig } from "next";
const config: NextConfig = {
  // Docker runs server.js; local npm start uses the normal Next.js build.
  output: process.env.BUILD_STANDALONE === "1" ? "standalone" : undefined,
};
export default config;
