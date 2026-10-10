import { test, expect } from "@playwright/test";
import { demoDetails, demoRun } from "../lib/demo-inbox";

for (const width of [1440, 390]) test(`full preview preserves the draft and approval does not send at ${width}px`, async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  let writes = 0;
  await page.route("**/api/v1/**", route => { if (route.request().method() !== "GET") writes++; return route.fulfill({ status: 500, json: {} }); });
  await page.setViewportSize({ width, height: 844 });
  await page.goto("/leads/demo-lead-1?demo=1");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByLabel("Reply draft")).toBeFocused();
  const text = "A full draft with no invented claims.\n" + "Known information ".repeat(130);
  await page.getByLabel("Reply draft").fill(text);
  await expect(page.locator(".reply-preview p")).toHaveText(text);
  await expect(page.locator(".reply-editor-meta")).toContainText(`${text.length} / 4000`);
  await page.getByRole("button", { name: "Approve draft" }).click();
  await expect(page.locator(".reply-state-approved")).toHaveText("APPROVED");
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  // Windows clipboard uses CRLF; compare source text after only that OS conversion.
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe(text);
  await expect(page.locator(".reply-notice")).toContainText("Approved reply copied");
  expect(writes).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Reply draft").fill("Edited after approval");
  await expect(page.locator(".reply-state-draft")).toHaveText("DRAFT");
});

test("generation reports accurate progress and errors without an approved draft", async ({ page }) => {
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/response")) { await gate; return route.fulfill({ status: 503, json: { error: { message: "Provider temporarily unavailable" } } }); }
    if (path.endsWith("/leads/csv-lead")) { const detail = demoDetails["demo-lead-1"]; return route.fulfill({ json: { ...detail, analysis: { ...detail.analysis, id: "csv-lead", provider_mode: "real" }, source: "csv" } }); }
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/leads/csv-lead");
  await page.getByRole("button", { name: "Generate suggested reply" }).click();
  await expect(page.locator(".reply-panel")).toContainText("Generating suggested reply");
  await expect(page.getByRole("button", { name: "Generate suggested reply" })).toBeDisabled();
  release!();
  await expect(page.locator(".reply-panel [role=alert]")).toContainText("Provider temporarily unavailable");
  await expect(page.getByRole("button", { name: "Approve draft" })).toBeDisabled();
  await expect(page.locator(".reply-panel")).toContainText("Approval stores your review; it does not send a message.");
});


test("copy confirmation is visible after a connected save", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  let draft = { analysis_id: "saved-lead", response_text: "Original draft", status: "pending", provider_mode: "real", updated_at: "2026-10-10T00:00:00Z" };
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/response")) { draft = { ...draft, ...route.request().postDataJSON() }; return route.fulfill({ json: draft }); }
    if (path.endsWith("/leads/saved-lead")) { const d = demoDetails["demo-lead-1"]; return route.fulfill({ json: { ...d, analysis: { ...d.analysis, id: "saved-lead" }, response_draft: draft, source: "csv" } }); }
    if (path.includes("/analysis/runs/")) return route.fulfill({ json: demoRun });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/leads/saved-lead");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Reply draft").fill("Exact saved reply");
  await page.getByRole("button", { name: "Save reply", exact: true }).click();
  await expect(page.locator(".reply-notice")).toContainText("Reply saved to the server");
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(page.locator(".reply-notice")).toContainText("Draft copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("Exact saved reply");
});
