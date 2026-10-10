import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Every API request stays offline; no credentials or real provider calls.
  await page.route("**/api/v1/**", route => route.fulfill({ status: 401,
    json: { error: { message: "Offline integration check" } } }));
});

test("landing copy describes real analysis and brand assets are served", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.locator("#main-content")).toContainText("real AI provider-backed analysis");
  await expect(page.locator("#main-content")).not.toContainText("MockProvider");
  const asset = await request.get("/brand/signalx.png");
  expect(asset.status()).toBe(200);
  expect(asset.headers()["content-type"]).toContain("image/png");
});

test("new mobile navigation closes through its backdrop without overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/products?demo=1");
  const toggle = page.getByRole("button", { name: "Toggle workspace navigation" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const backdrop = page.getByRole("button", { name: "Close workspace navigation" });
  await expect(backdrop).toBeVisible();
  await backdrop.click({ position: { x: 380, y: 100 } });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("latest route motion respects reduced-motion preferences", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/leads?demo=1");
  await expect(page.locator(".workspace-route-transition")).toHaveCount(1);
  expect(await page.locator(".workspace-route-transition").evaluate(element =>
    parseFloat(getComputedStyle(element).animationDuration))).toBeLessThanOrEqual(0.001);
});
