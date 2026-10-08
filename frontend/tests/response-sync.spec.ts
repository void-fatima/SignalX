import { test, expect } from "@playwright/test";
import { demoDetails, demoRun } from "../lib/demo-inbox";
import type { FeedbackOut, ResponseDraft } from "../lib/api";
const id = "csv-lead", source = demoDetails["demo-lead-1"];

test("CSV generation edits Save Cancel review and feedback persist without delivery", async ({ page }) => {
  let draft: ResponseDraft | null = null, feedback: FeedbackOut | null = null;
  const writes: { path: string; body: unknown }[] = [];
  await page.route("**/api/v1/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (request.method() !== "GET") {
      writes.push({ path, body: request.postData() ? request.postDataJSON() : null });
      if (path.endsWith("/response")) {
        draft = request.method() === "POST" ? { analysis_id: id, response_text: "Backend-generated grounded draft", status: "pending", provider_mode: "mock", updated_at: "2026-10-08T00:00:00Z" } : { ...draft!, ...request.postDataJSON() };
        return route.fulfill({ json: draft });
      }
      if (path.endsWith("/feedback")) { feedback = { ...request.postDataJSON(), analysis_id: id, updated_at: "2026-10-08T00:00:00Z" }; return route.fulfill({ json: feedback }); }
      throw new Error(`Unexpected delivery operation: ${path}`);
    }
    if (path.endsWith(`/leads/${id}`)) return route.fulfill({ json: { ...source, analysis: { ...source.analysis, id }, source: "csv", response_draft: draft, feedback } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto(`/leads/${id}`);
  await expect(page.getByLabel("Reply draft")).toHaveValue(""); expect(writes).toHaveLength(0);
  await page.getByRole("button", { name: "Generate suggested reply" }).click();
  await expect(page.getByLabel("Reply draft")).toHaveValue("Backend-generated grounded draft");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Reply draft").fill("Discarded edit");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(writes).toHaveLength(1);
  await expect(page.getByLabel("Reply draft")).toHaveValue("Backend-generated grounded draft");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Reply draft").fill("Exact saved edit");
  await expect(page.getByRole("button", { name: "Approve draft" })).toBeDisabled();
  await page.getByRole("button", { name: "Save reply", exact: true }).click();
  await expect(page.getByRole("button", { name: "Approve draft" })).toBeEnabled();
  await page.getByRole("button", { name: "Approve draft" }).click();
  await expect(page.locator(".reply-heading .badge")).toHaveText("APPROVED");
  await page.getByRole("button", { name: "Not relevant", exact: true }).click();
  await page.getByLabel("Comment", { exact: false }).fill("Needs a more specific fit.");
  await page.getByRole("button", { name: "Save feedback" }).click();
  await expect(page.locator(".feedback-save")).toContainText("saved to the server");
  await page.reload();
  await expect(page.getByLabel("Reply draft")).toHaveValue("Exact saved edit");
  await expect(page.locator(".reply-heading .badge")).toHaveText("APPROVED");
  await expect(page.getByRole("button", { name: "Not relevant", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(writes.map(value => value.body)).toEqual([null, { response_text: "Exact saved edit", status: "edited" }, { status: "approved" }, { relevant: false, comment: "Needs a more specific fit." }]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/persisted-reply-mobile.png", fullPage: true });
});

test("unavailable response contract reports error without claiming a saved draft", async ({ page }) => {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/response")) return route.fulfill({ status: 404, json: { error: { message: "Response API unavailable on this backend" } } });
    if (path.endsWith(`/leads/${id}`)) return route.fulfill({ json: { ...source, analysis: { ...source.analysis, id } } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto(`/leads/${id}`);
  await page.getByRole("button", { name: "Generate suggested reply" }).click();
  await expect(page.locator(".reply-panel [role=alert]")).toContainText("unavailable");
  await expect(page.getByLabel("Reply draft")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Approve draft" })).toBeDisabled();
});

test("overview uses persisted relevance rates and identifies incomplete provider cost", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("signalx:account", "owner"); localStorage.setItem("run_id", "analytics-run"); });
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: { ...demoRun, id: "analytics-run", config_snapshot: { provider_mode: "real" } } });
    if (path.endsWith("/analytics/overview")) return route.fulfill({ json: { run_id: "analytics-run", provider_mode: "real", total_count: 20, qualified_leads: 3, review_count: 2, failed_count: 0, total_cost_usd: "0.025", cost_per_message: null, cost_per_qualified_lead: null, unknown_usage_count: 1, cost_complete: false, feedback_acceptance: 0, feedback_coverage: 0.5 } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/dashboard");
  await expect(page.locator(".overview-feedback .feedback-ratio")).toHaveText("0%");
  await expect(page.locator(".overview-feedback")).toContainText("Feedback coverage: 50%");
  await expect(page.locator(".overview-metric").last()).toContainText("known portion");
  await expect(page.locator(".overview-feedback")).toContainText("1 usage records have unknown cost");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/analytics-mobile.png", fullPage: true });
});
