import { test, expect } from "@playwright/test";
import { telegramLead as lead, mockTelegram } from "./fixtures/telegram";
import type { TelegramLead } from "../lib/telegram";
const draft: TelegramLead = { ...lead, analysis: { ...lead.analysis, suggested_reply: "Exact approved reply" } };
const failed: TelegramLead = { ...draft, delivery: { ...lead.delivery, status: "failed", failure_category: "rate_limited", failure_http_status: 429, approved_text: "Exact approved reply", retry_after_at: null, delivery_uncertain: false } };

test("definitive failure acknowledges old key then deliberate retry uses new key", async ({ page }) => {
  await mockTelegram(page, draft);
  const keys: string[] = [], texts: string[] = [];
  let current = draft;
  await page.route("**/leads/*/telegram", route => route.fulfill({ json: current }));
  await page.route("**/telegram/reply", route => {
    keys.push(route.request().headers()["idempotency-key"]); texts.push(route.request().postDataJSON().text);
    if (keys.length === 1) { current = failed; return route.fulfill({ status: 502, json: { error: { message: "Failure acknowledgement lost" } } }); }
    if (keys.length === 2) return route.fulfill({ json: failed });
    current = { ...draft, delivery: { ...lead.delivery, status: "sent", telegram_message_id: 99 } }; return route.fulfill({ json: current });
  });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.getByRole("button", { name: "Check send request" })).toBeEnabled();
  await page.reload();
  await page.getByRole("button", { name: "Check send request" }).click();
  await expect(page.getByRole("button", { name: "Approve & Retry" })).toBeEnabled();
  expect(keys[1]).toBe(keys[0]);
  await page.getByRole("button", { name: "Approve & Retry" }).click();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Sent");
  expect(keys[2]).not.toBe(keys[0]); expect(texts).toEqual(Array(3).fill("Exact approved reply"));
});

test("cooldown ending enables explicit retry without sending automatically", async ({ page }) => {
  await mockTelegram(page, { ...failed, delivery: { ...failed.delivery, retry_after_at: new Date(Date.now() + 5000).toISOString() } });
  let sends = 0;
  await page.route("**/telegram/reply", route => { sends++; return route.fulfill({ json: failed }); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.getByRole("button", { name: "Approve & Retry" })).toBeDisabled();
  await expect(page.locator(".telegram-delivery")).toContainText("Nothing is resent automatically");
  await expect(page.getByRole("button", { name: "Approve & Retry" })).toBeEnabled({ timeout: 10000 });
  expect(sends).toBe(0);
  await page.screenshot({ path: "test-results/telegram-retry-desktop.png", fullPage: true });
});

test("uncertain delivery requires reconciliation even with a persisted intent", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockTelegram(page, { ...failed, delivery: { ...failed.delivery, delivery_uncertain: true } });
  await page.addInitScript(({ id }) => sessionStorage.setItem(`signalx:intent:telegram:owner:${id}`, JSON.stringify({ key: "same-request", text: "Exact approved reply" })), { id: lead.id });
  let sends = 0;
  await page.route("**/telegram/reply", route => { sends++; return route.fulfill({ json: failed }); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.getByRole("button", { name: "Check send request" })).toBeDisabled();
  await expect(page.locator(".telegram-delivery")).toContainText("reconcile delivery");
  expect(sends).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/telegram-uncertain-mobile.png", fullPage: true });
});

test("an omitted estimated cost remains unavailable", async ({ page }) => {
  await mockTelegram(page, { ...draft, analysis: { ...draft.analysis, usage: [{ stage: "reply", attempt_no: 1, provider_mode: "real", cost_status: "known", outcome: "success" }] } });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.getByLabel("Provider usage")).toContainText("Cost unavailable");
  await expect(page.getByLabel("Provider usage")).not.toContainText("undefined");
});
