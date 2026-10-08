import { test, expect } from "@playwright/test";
import { telegramLead as lead, mockTelegram } from "./fixtures/telegram";
const withDraft = { ...lead, analysis: { ...lead.analysis, suggested_reply: "Hi! What would you like to learn?" } };

test("null draft requires explicit generation and classification never sends", async ({ page }) => {
  await mockTelegram(page);
  let generations = 0, sends = 0;
  await page.route("**/telegram/suggested-reply", route => { generations++; expect(route.request().postDataJSON()).toEqual({ regenerate: false }); return route.fulfill({ json: withDraft }); });
  await page.route("**/telegram/reply", route => { sends++; return route.fulfill({ json: withDraft }); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  const approve = page.getByRole("button", { name: "Approve & Reply", exact: true });
  await expect(approve).toBeDisabled();
  expect(generations).toBe(0); expect(sends).toBe(0);
  await page.getByRole("button", { name: "Generate suggested reply", exact: true }).click();
  await expect(page.locator(".telegram-reply-text")).toHaveText(withDraft.analysis.suggested_reply);
  await expect(approve).toBeEnabled();
  expect(generations).toBe(1); expect(sends).toBe(0);
});

test("Save Cancel and regeneration preserve unsaved edits across refresh and navigation", async ({ page }) => {
  await mockTelegram(page, withDraft);
  let generations = 0;
  await page.route("**/telegram/suggested-reply", route => { generations++; expect(route.request().postDataJSON()).toEqual({ regenerate: true }); return route.fulfill({ json: { ...withDraft, analysis: { ...withDraft.analysis, suggested_reply: "A newly generated draft" } } }); });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Edit reply", exact: true }).click();
  await page.getByLabel("Reply draft", { exact: true }).fill("سلام! چه چیزی می‌خواهید یاد بگیرید؟");
  await expect(page.getByLabel("Reply draft", { exact: true })).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("button", { name: "Generate again", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Refresh delivery status", exact: true }).click();
  await expect(page.getByLabel("Reply draft", { exact: true })).toHaveValue("سلام! چه چیزی می‌خواهید یاد بگیرید؟");
  await page.getByRole("link", { name: "Back to inbox", exact: true }).click();
  await page.getByRole("link", { name: "Review lead", exact: true }).click();
  await expect(page.getByLabel("Reply draft", { exact: true })).toHaveValue("سلام! چه چیزی می‌خواهید یاد بگیرید؟");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator(".telegram-reply-text")).toHaveText(withDraft.analysis.suggested_reply);
  await page.getByRole("button", { name: "Generate again", exact: true }).click();
  await expect(page.locator(".telegram-reply-text")).toHaveText("A newly generated draft");
  expect(generations).toBe(1);
});

test("approval submits exact saved edits once and REVIEW is not human approval", async ({ page }) => {
  await mockTelegram(page, { ...withDraft, analysis: { ...withDraft.analysis, scoring: { score: 60, decision: "REVIEW" } } });
  const posted: { path: string; text: string }[] = [];
  await page.route("**/telegram/reply", async route => {
    posted.push({ path: new URL(route.request().url()).pathname, text: route.request().postDataJSON().text });
    await new Promise(resolve => setTimeout(resolve, 200));
    await route.fulfill({ json: { ...withDraft, delivery: { ...lead.delivery, status: "sent", telegram_message_id: 19 } } });
  });
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await expect(page.locator(".telegram-signal .decision")).toHaveText("Review");
  await expect(page.locator(".telegram-reply .badge")).toHaveText("DRAFT");
  await page.getByRole("button", { name: "Edit reply", exact: true }).click();
  const exact = "  Hello 👋\nمتن تأیید شده.  ";
  await page.getByLabel("Reply draft", { exact: true }).fill(exact);
  await page.getByRole("button", { name: "Save reply", exact: true }).click();
  expect(posted).toHaveLength(0);
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sending…", exact: true })).toBeDisabled();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Sent");
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  expect(posted).toEqual([{ path: `/api/v1/leads/${lead.id}/telegram/reply`, text: exact }]);
});

test("provider failure refreshes authoritative draft without inventing a reply or sending", async ({ page }) => {
  await mockTelegram(page);
  let sends = 0;
  await page.route("**/telegram/reply", route => { sends++; return route.fulfill({ status: 500 }); });
  await page.route("**/telegram/suggested-reply", route => route.fulfill({ status: 502, json: { error: { code: "reply_generation_failed", message: "Suggested reply generation failed; nothing was sent", details: [] } } }));
  await page.goto(`/leads/${lead.id}?source=telegram`);
  await page.getByRole("button", { name: "Generate suggested reply", exact: true }).click();
  await expect(page.locator(".telegram-action-error")).toContainText("nothing was sent");
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  expect(sends).toBe(0);
});

test("cross-origin and invalid approval requests are rejected by the frontend bridge", async ({ request }) => {
  const path = `/api/v1/leads/${lead.id}/telegram/reply`;
  const foreign = await request.post(path, { headers: { Origin: "https://untrusted.example" }, data: { text: "Must not send" } });
  expect(foreign.status()).toBe(403);
  const invalid = await request.post(path, { headers: { Origin: "http://localhost:3100" }, data: { text: "  " } });
  expect(invalid.status()).toBe(422);
  const signedOut = await request.post(path, { headers: { Origin: "http://localhost:3100" }, data: { text: "Reviewed reply" } });
  expect(signedOut.status()).toBe(401);
});
