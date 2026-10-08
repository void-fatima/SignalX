import { test, expect } from "@playwright/test";
import { demoDetails, demoRun } from "../lib/demo-inbox";

test("an explicit analysis link selects its lead and dismisses without reopening", async ({ page }) => {
  await page.goto("/leads?demo=1&lead_id=demo-lead-5&analysis=1");
  const dialog = page.getByRole("dialog", { name: "Signal analysis" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".dialog-source-meta")).toContainText("Navid");
  await expect(dialog.locator(".dialog-score-value strong")).toHaveText("48");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(page).not.toHaveURL(/analysis=1/);
  await expect(page.getByRole("button", { name: "Open signal analysis for Navid" })).toBeFocused();
  await page.getByRole("button", { name: /Mina 84/ }).click();
  await page.getByRole("button", { name: "Open signal analysis for Mina" }).click();
  await expect(dialog.locator(".dialog-score-value strong")).toHaveText("84");
});

test("missing analysis targets do not substitute another lead in the dialog", async ({ page }) => {
  await page.goto("/leads?demo=1&lead_id=missing&analysis=1");
  await expect(page.getByText("The requested opportunity is not available on this page. Choose a result or adjust your filters.")).toBeVisible();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("failed source loading keeps the modal closed until a successful retry", async ({ page }) => {
  let fail = true;
  const detail = demoDetails["demo-lead-1"];
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/leads/demo-lead-1")) return route.fulfill(fail ? { status: 503, json: { error: { message: "Source unavailable" } } } : { json: detail });
    if (path.endsWith("/leads")) return route.fulfill({ json: { items: [detail.analysis], total: 1, offset: 0, limit: 20 } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/leads?run_id=demo-run-024&lead_id=demo-lead-1&analysis=1");
  await expect(page.getByRole("heading", { name: "Source could not be loaded" })).toBeVisible();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Retry source details" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").locator(".dialog-score-value strong")).toHaveText("84");
});

test("New analysis preserves explicit demo mode", async ({ page }) => {
  await page.goto("/leads?demo=1");
  await page.getByRole("link", { name: "New analysis", exact: true }).click();
  await expect(page).toHaveURL(/\/imports\?demo=1$/);
});

for (const viewport of [{ width: 1280, height: 860 }, { width: 390, height: 844 }, { width: 360, height: 600 }]) {
  test(`analysis heading and return action stay available at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/leads?demo=1&lead_id=demo-lead-1&analysis=1");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const close = dialog.getByRole("button", { name: "Close signal analysis" });
    const back = dialog.getByRole("button", { name: "Back to conversation" });
    await expect(close).toBeInViewport(); await expect(back).toBeInViewport();
    await page.screenshot({ path: `test-results/analysis-modal-${viewport.width}x${viewport.height}.png` });
    const content = dialog.getByRole("region", { name: "Signal analysis details" });
    await content.focus(); await page.keyboard.press("End");
    await expect(back).toBeInViewport(); await expect(close).toBeInViewport();
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: `test-results/analysis-modal-${viewport.width}x${viewport.height}-scrolled.png` });
    await back.click(); await expect(dialog).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Open signal analysis for Mina" })).toBeFocused();
  });
}
