import { test, expect } from "@playwright/test";
import { telegramLead as lead, mockTelegram } from "./fixtures/telegram";

test("Telegram inbox opens contract metadata and evidence without a shared Mock schema", async ({ page }) => {
  await mockTelegram(page);
  await page.goto("/leads?source=telegram");
  await page.getByRole("link", { name: "Review lead", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review Telegram lead" })).toBeVisible();
  await expect(page.getByText("@test_user", { exact: true })).toBeVisible();
  await expect(page.locator(".telegram-community")).toContainText("Chat -100123 · Message 7 · Topic 3");
  await expect(page.locator(".telegram-original")).toContainText("09:00 UTC");
  await expect(page.locator(".telegram-score")).toContainText("76/100");
  await expect(page.locator(".telegram-evidence")).toContainText("Author states a need");
  await expect(page.locator(".telegram-original mark")).toHaveText(lead.original_message.text);
  await expect(page.locator(".telegram-destination")).toContainText("Reply to Message 7 · Topic 3");
  await page.getByRole("button", { name: "View analysis", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(lead.analysis.decision_reason!);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "View analysis", exact: true })).toBeFocused();
});

test("nullable topic username and qualification stay unavailable without fabricated values", async ({ page }) => {
  await mockTelegram(page, { ...lead, original_message: { ...lead.original_message, sender_username: null, chat_title: null, message_thread_id: null }, analysis: { ...lead.analysis, scoring: null, qualification: null, decision_reason: null } });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.locator(".telegram-source")).toContainText("Sender 8");
  await expect(page.locator(".telegram-source")).not.toContainText("Topic");
  await expect(page.locator(".telegram-signal")).toContainText("Unavailable");
  await expect(page.locator(".telegram-evidence")).toContainText("No evidence returned");
});

test("feature errors and mismatched lead data do not fall back to demo", async ({ page }) => {
  await mockTelegram(page);
  await page.route("**/api/v1/leads/*/telegram", route => route.fulfill({ status: 503, json: { error: { code: "authentication_unavailable", message: "Backend authentication must be integrated", details: [] } } }));
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.locator(".workflow-error")).toContainText("Backend authentication must be integrated");
  await expect(page.locator(".telegram-source")).toHaveCount(0);
  await page.unroute("**/api/v1/leads/*/telegram");
  await page.goto("/leads/different-lead?source=telegram");
  await expect(page.locator(".workflow-error")).toContainText("does not match");
});

test("server bridge requires the existing session without contacting Telegram", async ({ request }) => {
  const response = await request.get(`/api/v1/leads/${lead.id}/telegram`);
  expect(response.status()).toBe(401);
  expect((await response.json()).error.code).toBe("authentication_required");
});

for (const width of [1753, 390]) test(`Telegram review and queue remain readable at ${width}px`, async ({ page }) => {
  await mockTelegram(page);
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1160 });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.locator(".telegram-destination")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/telegram-source-${width}.png`, fullPage: true });
  await page.goto("/leads?source=telegram");
  await expect(page.getByRole("link", { name: "Review lead", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
