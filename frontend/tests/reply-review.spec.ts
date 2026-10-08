import { test, expect } from "@playwright/test";
import { demoDetails, demoRun } from "../lib/demo-inbox";

test("review draft edits approvals and feedback stay local and follow the selected lead", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  let writes = 0;
  await page.route("**/api/v1/**", route => { if (route.request().method() !== "GET") writes++; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/leads/demo-lead-1?demo=1");
  await expect(page.getByRole("heading", { name: "Review suggested reply", exact: true })).toBeVisible();
  await expect(page.locator(".review-original mark")).toHaveCount(2);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Reply draft").fill("سلام مینا! روی چه پروژه‌ای کار می‌کنی؟");
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("سلام مینا!");
  await page.getByRole("button", { name: "Approve draft", exact: true }).click();
  await expect(page.locator(".reply-heading .badge")).toHaveText("APPROVED");
  await page.getByRole("button", { name: "Needs context", exact: true }).click();
  await page.getByLabel("Comment", { exact: false }).fill("Ask which project the author wants to build.");
  await page.getByRole("button", { name: "Save feedback", exact: true }).click();
  await expect(page.locator(".feedback-save")).toContainText("this session only");
  await page.getByRole("link", { name: "Back to inbox", exact: true }).click();
  await expect(page.getByLabel("Reply draft")).toHaveValue("سلام مینا! روی چه پروژه‌ای کار می‌کنی؟");
  await expect(page.getByRole("button", { name: "Approve draft", exact: true })).toBeDisabled();
  expect(writes).toBe(0);
});

test("mock regeneration is explicit and resets a reviewed draft", async ({ page }) => {
  await page.goto("/leads/demo-lead-1?demo=1");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await page.getByLabel("Reply language").selectOption("en");
  await page.getByRole("button", { name: "Generate again", exact: true }).click();
  await expect(page.getByLabel("Reply draft")).toHaveValue(/Hi Mina/);
  await expect(page.getByLabel("Reply draft")).toHaveAttribute("dir", "ltr");
  await expect(page.locator(".reply-heading .badge")).toHaveText("DRAFT");
  await expect(page.locator(".reply-notice")).toContainText("No provider was called");
});

test("connected source starts empty and requires explicit generation", async ({ page }) => {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/leads/lead-1")) { const d = demoDetails["demo-lead-1"]; return route.fulfill({ json: { ...d, analysis: { ...d.analysis, id: "lead-1", provider_mode: "real" } } }); }
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [] } });
  });
  await page.goto("/leads/lead-1");
  await expect(page.locator(".review-title .badge")).toHaveText("REAL PROVIDER");
  await expect(page.getByRole("button", { name: "Generate suggested reply", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Reply draft")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Approve draft", exact: true })).toBeDisabled();
});

test("unknown demo and API errors never substitute another lead", async ({ page }) => {
  await page.goto("/leads/missing?demo=1");
  await expect(page.locator(".workflow-error")).toContainText("does not exist");
  await page.route("**/api/v1/**", route => route.request().url().endsWith("/auth/me") ? route.fulfill({ json: { id: "owner", email: "owner@example.test" } }) : route.fulfill({ status: 503, json: { error: { message: "Source unavailable" } } }));
  await page.goto("/leads/lead-1");
  await expect(page.locator(".workflow-error")).toContainText("Source unavailable");
  await expect(page.locator(".review-identity")).toHaveCount(0);
});

for (const width of [1705, 390]) test(`reply review layout and evidence dialog at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1145 });
  await page.goto("/leads/demo-lead-1?demo=1");
  await expect(page.getByRole("button", { name: "Save feedback", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/reply-review-${width}.png`, fullPage: true });
  const opener = page.getByRole("button", { name: "Open signal analysis for Mina" });
  await opener.click(); await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape"); await expect(opener).toBeFocused();
});
