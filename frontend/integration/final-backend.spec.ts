import { test, expect, type Page } from "@playwright/test";
const backend = "http://localhost:8000";
async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("browser-owner@example.test");
  await page.getByLabel("Password", { exact: true }).fill("offline integration password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/products/);
  return (await page.request.get(`${backend}/__test/fixture`)).json();
}

test("real authenticated HTTP retry updates attempts and preserves successful results", async ({ page }) => {
  const fixture = await signIn(page);
  const before = await (await page.request.get(`${backend}/api/v1/analysis/runs/${fixture.run_id}`)).json();
  const originals = await (await page.request.get(`${backend}/api/v1/leads?run_id=${fixture.run_id}&limit=100`)).json();
  expect(originals.items.length).toBeGreaterThan(0);
  const detailBefore = await (await page.request.get(`${backend}/api/v1/leads/${originals.items[0].id}`)).json();
  expect((await page.request.patch(`${backend}/api/v1/products/${fixture.product_id}`, { data: { name: "Changed after analysis" } })).ok()).toBe(true);
  await page.goto(`/leads?run_id=${fixture.run_id}&status=failed`);
  await expect(page.locator(".conversation-panel")).toContainText("Failure category: Provider timeout");
  await page.getByRole("link", { name: "Open run recovery", exact: true }).click();
  await expect(page.getByRole("region", { name: "Analysis recovery" })).toContainText("Attempt 1");
  await page.getByRole("button", { name: "Retry failed analyses", exact: true }).click();
  await expect(page.getByRole("region", { name: "Analysis recovery" })).toContainText("Attempt 2");
  expect((await page.request.post(`${backend}/__test/process`)).ok()).toBe(true);
  await expect(page.getByRole("heading", { name: "Analysis complete", exact: true })).toBeVisible();
  const after = await (await page.request.get(`${backend}/api/v1/analysis/runs/${fixture.run_id}`)).json();
  expect(after.config_snapshot).toEqual(before.config_snapshot);
  const results = await (await page.request.get(`${backend}/api/v1/leads?run_id=${fixture.run_id}&limit=100`)).json();
  for (const original of originals.items) expect(results.items.find((item: { id: string }) => item.id === original.id)).toEqual(original);
  const detailAfter = await (await page.request.get(`${backend}/api/v1/leads/${originals.items[0].id}`)).json();
  expect(detailAfter.product_snapshot).toEqual(detailBefore.product_snapshot);
  await page.screenshot({ path: "playwright-report/connected/final-http-run-desktop.png", fullPage: true });
});

test("real Telegram reply HTTP acknowledgement returns Sent only after adapter success", async ({ page }) => {
  const fixture = await signIn(page);
  await page.goto(`/leads/${fixture.telegram.sent}?source=telegram`);
  await page.getByRole("button", { name: "Edit reply", exact: true }).click();
  const text = "  Approved HTTP reply\nwith exact whitespace  ";
  await page.getByLabel("Reply draft", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Save reply", exact: true }).click();
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Sent");
  await page.reload();
  await expect(page.locator(".telegram-reply-text")).toHaveText(text);
  const requests = await (await page.request.get(`${backend}/__test/deliveries`)).json();
  expect(requests.filter((item: { chat_id: number }) => item.chat_id === -100501)).toEqual([expect.objectContaining({ text, reply_parameters: expect.objectContaining({ message_id: 7 }) })]);
});

test("real 429 then HTTP 200 failed replay never claims Sent or sends on cooldown expiry", async ({ page }) => {
  const fixture = await signIn(page);
  await page.goto(`/leads/${fixture.telegram.rate}?source=telegram`);
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Failed");
  await page.getByRole("button", { name: "Check send request", exact: true }).click();
  await expect(page.getByRole("button", { name: "Check send request", exact: true })).toHaveCount(0);
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Failed");
  await expect(page.getByRole("button", { name: "Approve & Retry", exact: true })).toBeDisabled();
  await page.request.post(`${backend}/__test/expire/${fixture.telegram.rate}`);
  await page.getByRole("button", { name: "Refresh delivery status", exact: true }).click();
  await expect(page.getByRole("button", { name: "Approve & Retry", exact: true })).toBeEnabled();
  let requests = await (await page.request.get(`${backend}/__test/deliveries`)).json();
  expect(requests.filter((item: { chat_id: number }) => item.chat_id === -100502)).toHaveLength(1);
  await page.getByRole("button", { name: "Approve & Retry", exact: true }).click();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Sent");
  requests = await (await page.request.get(`${backend}/__test/deliveries`)).json();
  expect(requests.filter((item: { chat_id: number }) => item.chat_id === -100502)).toHaveLength(2);
});

test("real timeout persists uncertain delivery and preserves approval after mobile refresh", async ({ page }) => {
  const fixture = await signIn(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/leads/${fixture.telegram.uncertain}?source=telegram`);
  await page.getByRole("button", { name: "Approve & Reply", exact: true }).click();
  await expect(page.locator(".telegram-delivery-label")).toHaveText("Delivery uncertain");
  await page.reload();
  await expect(page.getByRole("button", { name: "Check send request", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Approve & Reply", exact: true })).toBeDisabled();
  const requests = await (await page.request.get(`${backend}/__test/deliveries`)).json();
  expect(requests.filter((item: { chat_id: number }) => item.chat_id === -100503)).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "playwright-report/connected/final-http-uncertain-mobile.png", fullPage: true });
});
