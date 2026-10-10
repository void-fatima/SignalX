import { test, expect } from "@playwright/test";
import { demoDetails, demoRun } from "../lib/demo-inbox";

for (const width of [1440, 390, 360]) test(`long grounded quotes wrap and modal focus is contained at ${width}px`, async ({ page }) => {
  const detail = structuredClone(demoDetails["demo-lead-1"]);
  const quote = "A long source quote with a URL-like unbroken word: " + "company".repeat(70);
  detail.message.content = quote;
  detail.analysis.evidence = [{ message_id: detail.message.id, quote }];
  detail.analysis.provider_mode = "real";
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith(`/leads/${detail.analysis.id}`)) return route.fulfill({ json: detail });
    if (path.endsWith("/leads")) return route.fulfill({ json: { items: [detail.analysis], total: 1, offset: 0, limit: 20 } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [] } });
  });
  await page.setViewportSize({ width, height: 844 });
  await page.goto(`/leads?run_id=${demoRun.id}&lead_id=${detail.analysis.id}&analysis=1`);
  const dialog = page.getByRole("dialog", { name: "Signal analysis" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("blockquote")).toHaveText(quote);
  await expect(dialog.locator(".dialog-evidence")).toContainText(detail.message.external_id);
  const widths = await dialog.evaluate(element => [element, ...element.querySelectorAll(".dialog-scroll-content, blockquote")].map(node => node.scrollWidth <= node.clientWidth));
  expect(widths.every(Boolean)).toBe(true);
  expect(await dialog.locator("blockquote").evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeLessThanOrEqual(16);
  for (let i = 0; i < 9; i++) { await page.keyboard.press("Tab"); expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true); }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open signal analysis for Mina" })).toBeFocused();
});
