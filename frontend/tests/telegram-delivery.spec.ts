import { test, expect } from "@playwright/test";
import { telegramLead as lead, mockTelegram } from "./fixtures/telegram";
import type { TelegramLead } from "../lib/telegram";
const withDraft: TelegramLead = { ...lead, analysis: { ...lead.analysis, suggested_reply: "A reviewed reply" } };

for (const status of ["sending", "sent", "failed"] as const) test(`persisted ${status} state blocks duplicate delivery`, async ({ page }) => {
  await mockTelegram(page, { ...withDraft, delivery: { ...lead.delivery, status, telegram_message_id: status === "sent" ? 21 : null, failure_category: status === "failed" ? "forbidden" : null } });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.locator(".telegram-delivery-label")).toHaveText(status === "sent" ? "Sent" : status === "sending" ? "Sending" : "Failed");
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  if (status === "sent") await expect(page.locator(".telegram-delivery")).toContainText("Delivered Telegram message 21. Original message 7");
});

for (const unavailable of ["uncertain", "draft_busy"]) test(`${unavailable} never allows generation or sending`, async ({ page }) => {
  await mockTelegram(page, { ...withDraft, delivery: { ...lead.delivery, delivery_uncertain: unavailable === "uncertain", draft_busy: unavailable === "draft_busy" } });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Generate again", exact: true })).toBeDisabled();
  await expect(page.locator(".telegram-delivery")).toContainText(unavailable === "uncertain" ? "Check the original Telegram thread" : "A draft operation is already active");
});

for (const state of ["sent", "uncertain", "not_sent", "unavailable"] as const) test(`502 refreshes persisted ${state} without retrying POST`, async ({ page }) => {
  await mockTelegram(page, withDraft);
  let posts = 0, readsAfterSend = 0;
  await page.route("**/api/v1/leads/*/telegram", route => {
    if (posts) readsAfterSend++;
    if (posts && state === "unavailable") return route.fulfill({ status: 503, json: { error: { code: "unavailable", message: "Delivery cannot be verified", details: [] } } });
    return route.fulfill({ json: posts && state !== "not_sent" ? { ...withDraft, delivery: { ...lead.delivery, status: state === "sent" ? "sent" : "failed", delivery_uncertain: state === "uncertain", telegram_message_id: state === "sent" ? 77 : null } } : withDraft });
  });
  await page.route("**/telegram/reply", route => { posts++; return route.fulfill({ status: 502, json: { error: { code: "telegram_delivery_failed", message: "Delivery could not be confirmed", details: [] } } }); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.locator(".telegram-action-error")).toContainText("could not be confirmed");
  await expect(page.getByRole("button", { name: "Refresh delivery status", exact: true })).toBeEnabled();
  expect(readsAfterSend).toBeGreaterThan(0);
  expect(posts).toBe(1);
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  await expect(page.locator(".telegram-delivery")).toContainText(state === "sent" ? "Delivered Telegram message 77" : "Check the original Telegram thread");
  if (state === "not_sent") {
    await page.reload();
    await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
    await expect(page.locator(".telegram-delivery-label")).toHaveText("Delivery uncertain");
  }
  expect(posts).toBe(1);
});

test("network failure remains blocked and never automatically retries", async ({ page }) => {
  await mockTelegram(page, withDraft);
  let sends = 0;
  await page.route("**/telegram/reply", route => { sends++; return route.abort("failed"); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Delivery uncertain");
  await page.getByRole("button", { name: "Refresh delivery status", exact: true }).click();
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  expect(sends).toBe(1);
});

test("409 draft conflict refreshes server state and preserves edited reply", async ({ page }) => {
  await mockTelegram(page, withDraft);
  let conflict = false;
  await page.route("**/api/v1/leads/*/telegram", route => route.fulfill({ json: { ...withDraft, delivery: { ...lead.delivery, draft_busy: conflict } } }));
  await page.route("**/telegram/reply", route => { conflict = true; return route.fulfill({ status: 409, json: { error: { code: "delivery_requires_review", message: "A draft operation is in progress", details: [] } } }); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Edit reply", exact: true }).click();
  await page.getByLabel("Reply draft", { exact: true }).fill("My reviewed edits");
  await page.getByRole("button", { name: "Save reply", exact: true }).click();
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.locator(".telegram-delivery")).toContainText("A draft operation is already active");
  await expect(page.locator(".telegram-reply-text")).toHaveText("My reviewed edits");
});

for (const operation of ["suggested-reply", "reply"] as const) test(`late ${operation} response stays with its original lead`, async ({ page }) => {
  const second: TelegramLead = { ...withDraft, id: "00000000-0000-0000-0000-000000000005", original_message: { ...lead.original_message, sender_display_name: "Second sender", chat_id: -100456, message_id: 9 }, analysis: { ...withDraft.analysis, suggested_reply: "Reply for the second lead" } };
  await mockTelegram(page, operation === "reply" ? withDraft : lead);
  await page.route("**/integrations/telegram/leads?**", route => route.fulfill({ json: { items: [lead, second], total: 2, limit: 20, offset: 0 } }));
  await page.route(`**/leads/${second.id}/telegram`, route => route.fulfill({ json: second }));
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let target = "";
  await page.route(`**/telegram/${operation}`, async route => {
    target = new URL(route.request().url()).pathname;
    await pending;
    await route.fulfill({ json: { ...withDraft, analysis: { ...withDraft.analysis, suggested_reply: "Late draft from first lead" }, delivery: { ...lead.delivery, status: operation === "reply" ? "sent" : "not_sent" } } });
  });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: operation === "reply" ? "Approve & Reply" : "Generate suggested reply", exact: true }).click();
  await expect.poll(() => target).toBe(`/api/v1/leads/${lead.id}/telegram/${operation}`);
  await page.getByRole("link", { name: "Back to inbox", exact: true }).click();
  await page.getByRole("row").filter({ hasText: "Second sender" }).getByRole("link", { name: "Review lead", exact: true }).click();
  release();
  await expect(page.locator(".review-identity")).toContainText("Second sender");
  await expect(page.locator(".telegram-reply-text")).toHaveText("Reply for the second lead");
  await expect(page.locator(".telegram-destination")).toContainText("Reply to Message 9");
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Not sent");
});

test("demo query cannot trigger connected Telegram requests", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/v1/**", route => { requests++; return route.fulfill({ status: 500 }); });
  await page.goto(`/leads/${lead.id}?source=telegram&demo=1`);
  await expect(page.locator(".workflow-error")).toContainText("Exit demo");
  await page.getByRole("button", { name: "Refresh lead", exact: true }).click();
  expect(requests).toBe(0);
});

test("quotes absent from the original message or tied to another source are never highlighted", async ({ page }) => {
  await mockTelegram(page, { ...lead, analysis: { ...lead.analysis, qualification: { ...lead.analysis.qualification!, evidence: [{ message_id: lead.message_id, quote: "Absent from original", reason: "Unverified" }, { message_id: "other-message", quote: lead.original_message.text, reason: "Other source" }] } } });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.locator(".telegram-original blockquote")).toHaveText(lead.original_message.text);
  await expect(page.locator(".telegram-original mark")).toHaveCount(0);
});

test("provider attempts label Mock costs and preserve unknown real costs", async ({ page }) => {
  const usage = { stage: "reply", attempt_no: 1, model: null, input_tokens: null, output_tokens: null, price_version: null, latency_ms: null, outcome: "success" };
  await mockTelegram(page, { ...withDraft, analysis: { ...withDraft.analysis, usage: [{ ...usage, provider_mode: "mock", estimated_cost: "0", cost_status: "mock" }, { ...usage, provider_mode: "real", estimated_cost: null, cost_status: "unknown" }] } });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.getByLabel("Provider usage")).toContainText("MOCK");
  await expect(page.getByLabel("Provider usage")).toContainText("Mock cost: $0");
  await expect(page.getByLabel("Provider usage")).toContainText("Cost unavailable");
});

test("switching authenticated accounts clears the previous account's local edits", async ({ page }) => {
  await mockTelegram(page, withDraft);
  let owner = "first-owner";
  await page.route("**/auth/me", route => route.fulfill({ json: { id: owner, email: `${owner}@example.test` } }));
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Edit reply", exact: true }).click();
  await page.getByLabel("Reply draft", { exact: true }).fill("Private edits for first account");
  owner = "second-owner";
  await page.getByRole("link", { name: "Back to inbox", exact: true }).click();
  await expect(page.locator(".workspace-profile")).toContainText("second-owner");
  await page.getByRole("link", { name: "Review lead", exact: true }).click();
  await expect(page.getByLabel("Reply draft", { exact: true })).toHaveCount(0);
  await expect(page.locator(".telegram-reply-text")).toHaveText(withDraft.analysis.suggested_reply!);
});

for (const width of [1753, 390]) test(`complete Telegram reply controls at ${width}px`, async ({ page }) => {
  await mockTelegram(page, withDraft);
  await page.setViewportSize({ width, height: width === 390 ? 844 : 1160 });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/telegram-review-${width}.png`, fullPage: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: "Edit reply", exact: true }).click();
  await expect(page.getByLabel("Reply draft", { exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Save reply", exact: true })).toBeFocused();
});
