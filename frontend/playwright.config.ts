import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests", fullyParallel: true, workers: 2, timeout: 30_000,
  reporter: "list",
  use: { baseURL: "http://localhost:3100", channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === "win32" ? "msedge" : undefined), headless: true, viewport: { width: 1728, height: 1170 }, screenshot: "only-on-failure", trace: "retain-on-failure" },
  // Server bridge tests target only the local fake HTTP server, never a real bot.
  webServer: { command: "npm run start -- --port 3100", url: "http://localhost:3100", reuseExistingServer: false, timeout: 60_000, env: { BACKEND_API_URL: "http://127.0.0.1:3201/api/v1" } },
});
