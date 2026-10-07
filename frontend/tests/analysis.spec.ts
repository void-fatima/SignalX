import { test, expect } from "@playwright/test";
import { demoAnalyses, demoDetails, demoRun } from "../lib/demo-inbox";
import { demoProduct } from "../lib/product-profile";

test("analysis reference is a static mock snapshot with working review links", async ({ page }) => {
  await page.setViewportSize({ width: 1285, height: 900 });
  let calls = 0;
  await page.route("**/api/v1/**", route => { calls++; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/runs/demo-run-024?demo=1");
  await expect(page.getByRole("heading", { name: "Analysis in progress", exact: true })).toBeVisible();
  await expect(page.locator('.sidebar a[aria-current="page"]')).toHaveText("Imports");
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "14");
  await expect(page.locator(".progress-counts b")).toHaveText(["12", "2", "6"]);
  await expect(page.getByText("Static demo · updates off")).toBeVisible();
  await page.screenshot({ path: "test-results/analysis-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "View issues", exact: true }).click();
  await expect(page.locator("#run-issues")).toContainText("Synthetic example");
  await page.getByRole("link", { name: "Review Navid's result" }).click();
  await expect(page.getByRole("button", { name: "Open signal analysis for Navid" })).toBeVisible();
  expect(calls).toBe(0);
});

test("manual demo states expose completed partial and interrupted outcomes", async ({ page }) => {
  await page.goto("/runs/demo-run-024?demo=1");
  await page.getByText("Demo status previews", { exact: true }).click();
  await page.getByLabel("Demo run state").selectOption("completed");
  await expect(page.getByRole("heading", { name: "Analysis complete", exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20");
  await page.getByLabel("Demo run state").selectOption("partial");
  await expect(page.getByRole("heading", { name: "Analysis partially complete", exact: true })).toBeVisible();
  await expect(page.locator(".progress-counts b")).toHaveText(["18", "2", "0"]);
  await page.getByLabel("Demo run state").selectOption("interrupted");
  await page.getByRole("button", { name: "View issues", exact: true }).click();
  await expect(page.getByRole("link", { name: "Open Imports to create a new run" })).toBeVisible();
});

test("connected run polls to completion and shows actual message results", async ({ page }) => {
  let polls = 0;
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/analysis/runs/run-1")) { polls++; return route.fulfill({ json: { ...demoRun, id: "run-1", status: polls === 1 ? "running" : "completed", processed_count: polls === 1 ? 14 : 20, config_snapshot: { provider_mode: "real" } } }); }
    if (url.pathname.endsWith("/leads")) return route.fulfill({ json: { items: [{ ...demoAnalyses[1], run_id: "run-1" }], total: 1 } });
    if (url.pathname.includes("/leads/")) { const detail = demoDetails["demo-lead-2"]; return route.fulfill({ json: { ...detail, analysis: { ...detail.analysis, run_id: "run-1" } } }); }
    return route.fulfill({ json: url.pathname.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [demoProduct] } });
  });
  await page.goto("/runs/run-1");
  await expect(page.getByText(/Updates automatically/)).toBeVisible();
  await expect(page.locator(".arriving-results")).toContainText("Looking for a hands-on backend course");
  await expect(page.locator(".run-details")).toContainText("Unavailable");
  await expect(page.getByRole("heading", { name: "Analysis complete", exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("Final run status")).toBeVisible();
  await page.waitForTimeout(2300);
  expect(polls).toBe(2);
});

test("connection errors pause updates and recover on explicit retry", async ({ page }) => {
  let reads = 0;
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/analysis/runs/run-1")) { reads++; return reads === 1 ? route.fulfill({ status: 503, json: { error: { message: "Connection unavailable" } } }) : route.fulfill({ json: { ...demoRun, id: "run-1", status: "partial", failed_count: 2 } }); }
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [], total: 0 } });
  });
  await page.goto("/runs/run-1");
  await expect(page.locator(".workflow-error")).toContainText("Connection unavailable");
  expect(reads).toBe(1);
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(page.getByRole("heading", { name: "Analysis partially complete", exact: true })).toBeVisible();
  await expect(page.locator(".progress-counts b")).toHaveText(["18", "2", "0"]);
});

test("foreign source details never appear in the current run", async ({ page }) => {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/analysis/runs/run-1")) return route.fulfill({ json: { ...demoRun, id: "run-1" } });
    if (path.endsWith("/leads")) return route.fulfill({ json: { items: [{ ...demoAnalyses[0], run_id: "run-1" }], total: 1 } });
    if (path.includes("/leads/")) return route.fulfill({ json: { ...demoDetails["demo-lead-1"], message: { ...demoDetails["demo-lead-1"].message, author: "Foreign author", batch_id: "another-batch" } } });
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [] } });
  });
  await page.goto("/runs/run-1");
  await expect(page.getByText("Source unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("Foreign author", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry results" })).toBeVisible();
});

test("analysis mobile retains progress details issues and row actions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/runs/demo-run-024?demo=1");
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "14");
  await expect(page.getByRole("link", { name: "View available results" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/analysis-mobile.png", fullPage: true });
});
