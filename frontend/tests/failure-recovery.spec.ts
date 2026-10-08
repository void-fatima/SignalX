import { test, expect } from "@playwright/test";
import { demoAnalyses, demoDetails, demoRun } from "../lib/demo-inbox";
const failed = { ...demoRun, id: "run-recovery", status: "partial", failed_count: 2, attempt_no: 1 };

for (const outcome of ["server error", "unreadable response"]) test(`uncertain run retry (${outcome}) reuses its key across reload`, async ({ page }) => {
  const keys: string[] = [];
  let recovered = false;
  await page.route("**/api/v1/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/retry")) {
      keys.push(request.headers()["idempotency-key"]);
      expect(request.postData()).toBeNull();
      if (keys.length === 1) return outcome === "server error" ? route.fulfill({ status: 502, json: { error: { message: "Retry acknowledgement lost" } } }) : route.fulfill({ status: 422, contentType: "text/html", body: "<p>Unreadable gateway response</p>" });
      recovered = true; return route.fulfill({ status: 202, json: { ...failed, status: "queued", attempt_no: 2 } });
    }
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: recovered ? { ...failed, status: "completed", failed_count: 0, attempt_no: 2 } : failed });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/runs/run-recovery");
  await page.getByRole("button", { name: "Retry failed analyses" }).click();
  await expect(page.locator(".run-recovery [role=alert]")).toContainText(outcome === "server error" ? "acknowledgement lost" : "unreadable response");
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
  await expect(page.locator(".conversation-panel")).toContainText("Failure category: Provider timeout (provider_timeout)");
  await expect(page.getByRole("link", { name: "Open run recovery" })).toHaveAttribute("href", `/runs/${failed.id}`);
  await expect(page.locator(".signal-card-score")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Approve draft" })).toHaveCount(0);
  expect(failedReads).toBe(1);
  await page.screenshot({ path: "test-results/failed-leads-desktop.png", fullPage: true });
});

for (const category of [null, "future_category", "private exception: token=secret", "toString"]) test(`failure category ${category ?? "absent"} has safe fallback`, async ({ page }) => {
  const analysis = { ...demoAnalyses[0], status: "failed", failure_category: category, reason: "private raw exception", lead_score: null, decision: null };
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/leads")) return route.fulfill({ json: { items: [analysis], total: 1, limit: 20, offset: 0 } });
    if (path.includes("/leads/")) return route.fulfill({ json: { ...demoDetails[analysis.id], analysis } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: { ...failed, id: analysis.run_id } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto(`/leads?run_id=${analysis.run_id}&status=failed`);
  const panel = page.locator(".conversation-panel");
  await expect(panel).toContainText(`Failure category: ${category ? "Unrecognized category" : "Unavailable"}`);
  await expect(panel).not.toContainText("private raw exception");
  await expect(panel).not.toContainText("token=secret");
  await expect(panel.locator(".signal-card-score")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("link", { name: "Open run recovery" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (category === null) await page.screenshot({ path: "test-results/failed-category-mobile.png", fullPage: true });
  await page.goto(`/leads/${analysis.id}`);
  await expect(page.getByRole("heading", { name: "Analysis failed", exact: true })).toBeVisible();
  await expect(page.locator(".review-page")).not.toContainText("private raw exception");
  await expect(page.getByRole("link", { name: "Open run recovery" })).toHaveAttribute("href", `/runs/${analysis.run_id}`);
});

test("reload only reads status; pending retry locks duplicates; deliberate retries use new keys", async ({ page }) => {
  const keys: string[] = [];
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/retry")) {
      keys.push(route.request().headers()["idempotency-key"]);
      if (keys.length === 1) { await pending; return route.fulfill({ json: { id: failed.id, status: "unknown" } }); }
      return route.fulfill({ status: 202, json: { ...failed, attempt_no: 7 } });
    }
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: { ...failed, attempt_no: keys.length > 1 ? 7 : undefined } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto(`/runs/${failed.id}`);
  const recovery = page.getByRole("region", { name: "Analysis recovery" });
  await expect(recovery).toContainText("Attempt unavailable on this backend");
  await page.getByRole("button", { name: "Retry failed analyses" }).click();
  await expect(page.getByRole("button", { name: "Requesting retry…" })).toBeDisabled();
  expect(keys).toHaveLength(1);
  release();
  await expect(recovery.getByRole("alert")).toContainText("could not be verified");
  await page.getByRole("button", { name: "Reload run status", exact: true }).click();
  await expect(page.getByRole("button", { name: "Check retry request" })).toBeEnabled();
  expect(keys).toHaveLength(1);
  await page.getByRole("button", { name: "Check retry request" }).click();
  await expect(recovery).toContainText("Attempt 7");
  expect(keys[1]).toBe(keys[0]);
  await page.getByRole("button", { name: "Retry failed analyses" }).click();
  await expect.poll(() => keys.length).toBe(3);
  expect(keys[2]).not.toBe(keys[0]);
});
