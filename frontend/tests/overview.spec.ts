import { test, expect } from "@playwright/test";
import { demoRun, demoAnalyses, demoDetails } from "../lib/demo-inbox";

test("overview demo preserves mock mode and does not call the API", async ({ page }) => {
  await page.setViewportSize({ width: 1285, height: 900 });
  let requests = 0;
  await page.route("**/api/v1/**", route => { requests++; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/dashboard?demo=1");
  await expect(page.getByRole("heading", { name: "Workspace overview" })).toBeVisible();
  await expect(page.locator('.sidebar a[aria-current="page"]')).toHaveText("Overview");
  await expect(page.locator(".overview-metric strong")).toHaveText(["20", "9", "3", "$0.00"]);
  await expect(page.locator(".review-list li")).toHaveCount(2);
  await page.screenshot({ path: "test-results/overview-desktop.png", fullPage: true });
  expect(requests).toBe(0);
  await page.locator(".review-list a").first().click();
  await expect(page.getByRole("button", { name: "Open signal analysis for Navid" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Workspace overview" })).toBeVisible();
  await page.getByRole("link", { name: "New analysis", exact: true }).click();
  await expect(page).toHaveURL(/\/imports\?demo=1/);
});

test("connected overview uses API totals and never invents feedback", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("signalx:account", "owner"); localStorage.setItem("run_id", "run-1"); });
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/analysis/runs/run-1")) return route.fulfill({ json: { ...demoRun, id: "run-1", processed_count: 15 } });
    if (url.pathname.endsWith("/leads")) { const decision = url.searchParams.get("decision"); return route.fulfill({ json: { items: decision === "review" ? [demoAnalyses[4]] : [], total: decision === "respond" ? 2 : decision === "review" ? 3 : 10 } }); }
    if (url.pathname.includes("/leads/")) return route.fulfill({ json: demoDetails["demo-lead-5"] });
    return route.fulfill({ json: url.pathname.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [] } });
  });
  await page.goto("/dashboard");
  await expect(page.locator(".overview-metric strong")).toHaveText(["15", "5", "—", "$0.00"]);
  await expect(page.getByText("Review a conversation to view its saved feedback.")).toBeVisible();
});

test("overview mobile reflows and exposes navigation and table actions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard?demo=1");
  await expect(page.locator(".review-list li")).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/overview-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Toggle workspace navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Overview" })).toBeVisible();
});
