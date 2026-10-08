import { defineConfig } from "@playwright/test";
import path from "node:path";
const python = path.resolve("../backend/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

export default defineConfig({
  testDir: "./integration", outputDir: "./playwright-report/connected", workers: 1, timeout: 30_000, reporter: "list",
  use: { baseURL: "http://localhost:3100", channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === "win32" ? "msedge" : undefined), headless: true, screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: [
    { command: "npm run start -- --port 3100", url: "http://localhost:3100", reuseExistingServer: false, timeout: 60_000 },
    { command: `"${python}" -X utf8 integration/runtime.py`, url: "http://localhost:8000/__test/fixture", reuseExistingServer: false, timeout: 60_000 },
  ],
});
