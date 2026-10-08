import { test, expect } from "@playwright/test";
import { demoAnalyses, demoDetails, demoRun } from "../lib/demo-inbox";
const failed = { ...demoRun, id: "run-recovery", status: "partial", failed_count: 2, attempt_no: 1 };

test("uncertain run retry reuses its key across reload and stops after acknowledgement", async ({ page }) => {
  const keys: string[] = [];
  let recovered = false;
  await page.route("**/api/v1/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/retry")) {
      keys.push(request.headers()["idempotency-key"]);
      expect(request.postData()).toBeNull();
      if (keys.length === 1) return route.fulfill({ status: 502, json: { error: { message: "Retry acknowledgement lost" } } });
      recovered = true; return route.fulfill({ status: 202, json: { ...failed, status: "queued", attempt_no: 2 } });
    }
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: recovered ? { ...failed, status: "completed", failed_count: 0, attempt_no: 2 } : failed });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/runs/run-recovery");
  await page.getByRole("button", { name: "Retry failed analyses" }).click();
  await expect(page.locator(".run-recovery [role=alert]")).toContainText("acknowledgement lost");
  expect(keys).toHaveLength(1);
  await page.reload();
  await page.getByRole("button", { name: "Check retry request" }).click();
  await expect(page.getByRole("heading", { name: "Analysis complete", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Analysis recovery" })).toContainText("Attempt 2");
  expect(keys).toHaveLength(2); expect(keys[0]).toBeTruthy(); expect(keys[1]).toBe(keys[0]);
});

test("failed message listing omits decision and score and shows safe failure details", async ({ page }) => {
  const analysis = { ...demoAnalyses[0], run_id: failed.id, status: "failed", lead_score: null, decision: null, signals: null, evidence: [], failure_category: "provider_timeout", reason: "Analysis failed" };
  const detail = { ...demoDetails[analysis.id], analysis };
  let failedReads = 0;
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (url.pathname.endsWith("/leads")) {
      expect(url.searchParams.get("status")).toBe("failed"); expect(url.searchParams.has("decision")).toBe(false); expect(url.searchParams.has("min_score")).toBe(false); failedReads++;
      return route.fulfill({ json: { items: [analysis], total: 1, limit: 20, offset: 0 } });
    }
    if (url.pathname.includes("/leads/")) return route.fulfill({ json: detail });
    if (url.pathname.includes("/analysis/runs/")) return route.fulfill({ json: failed });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto(`/leads?run_id=${failed.id}&status=failed`);
  await expect(page.locator(".conversation-panel")).toContainText("The provider did not respond in time.");
  await expect(page.locator(".signal-card-score")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve draft" })).toHaveCount(0);
  expect(failedReads).toBe(1);
  await page.screenshot({ path: "test-results/failed-leads-desktop.png", fullPage: true });
});
