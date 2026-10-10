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


test("all six source signals retain their exact values and snapshots are readable", async ({ page }) => {
  await page.goto("/leads?demo=1&lead_id=demo-lead-1&analysis=1");
  const dialog = page.getByRole("dialog");
  const signals = demoDetails["demo-lead-1"].analysis.signals!;
  const rows = [["Purchase intent", signals.purchase_intent], ["Product fit", signals.product_fit], ["Need strength", signals.need_strength], ["Urgency", signals.urgency], ["Confidence", signals.confidence], ["Response opportunity", signals.response_opportunity]] as const;
  for (const [label, value] of rows) {
    await expect(dialog.getByRole("meter", { name: label, exact: true })).toHaveAttribute("aria-valuenow", String(value));
    await expect(dialog.locator(".breakdown-row").filter({ has: page.getByText(label, { exact: true }) })).toContainText(`${value.toFixed(2)} / 1`);
  }
  await dialog.locator(".product-snapshot summary").click();
  await expect(dialog.locator(".product-snapshot dd").first()).toHaveText("Backend Academy");
  await expect(dialog.locator(".product-snapshot")).toContainText("Not supplied");
  await expect(dialog.locator(".product-snapshot pre")).toHaveCount(0);
});

test("nullable signals stay unavailable and snapshot text is escaped", async ({ page }) => {
  const detail = structuredClone(demoDetails["demo-lead-1"]);
  detail.analysis.signals = null; detail.analysis.lead_score = null;
  detail.product_snapshot = { name: "LedgerFlow", description: "<script>window.bad=1</script>", target_customer: "Finance teams", not_fit: ["Needs offline installation"], price: null };
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith(`/leads/${detail.analysis.id}`)) return route.fulfill({ json: detail });
    if (path.endsWith("/leads")) return route.fulfill({ json: { items: [detail.analysis], total: 1, offset: 0, limit: 20 } });
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto(`/leads?run_id=${demoRun.id}&lead_id=${detail.analysis.id}&analysis=1`);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Signals are unavailable");
  await expect(dialog.getByRole("meter")).toHaveCount(0);
  await dialog.locator(".product-snapshot summary").click();
  await expect(dialog.locator(".product-snapshot")).toContainText("<script>window.bad=1</script>");
  await expect(dialog.locator(".product-snapshot")).toContainText("Needs offline installation");
  expect(await page.evaluate(() => "bad" in window)).toBe(false);
});
