import { test, expect } from "@playwright/test";
import { demoProduct } from "../lib/product-profile";

test("private pages wait for session and expiration hides their data", async ({ page }) => {
  let expired = false, productReads = 0;
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ status: expired ? 401 : 200, json: expired ? { error: { message: "Session expired" } } : { id: "owner", email: "owner@example.test" } });
    productReads++; return route.fulfill({ json: { items: [demoProduct], total: 1 } });
  });
  await page.goto("/products");
  await expect(page.getByLabel("Product name")).toHaveValue(demoProduct.name);
  await page.evaluate(() => { localStorage.setItem("run_id", "private-run"); });
  expired = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await expect(page.getByLabel("Product name")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("run_id"))).toBeNull();
  expect(productReads).toBe(1);
});

test("all owned profile pages support saved selection and keyboard details", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => { localStorage.setItem("signalx:account", "owner"); localStorage.setItem("product_id", "second"); });
  const offsets: string[] = [];
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (url.pathname.endsWith("/products/second")) return route.fulfill({ json: { ...demoProduct, id: "second", name: "Second profile", price: "0" } });
    offsets.push(url.searchParams.get("offset") || "0");
    return route.fulfill({ json: { items: [{ ...demoProduct, id: url.searchParams.get("offset") === "1" ? "second" : "first", name: url.searchParams.get("offset") === "1" ? "Second profile" : "First profile" }], total: 2, limit: 1 } });
  });
  await page.goto("/products");
  await expect(page.getByLabel("Product name")).toHaveValue("Second profile");
  expect(offsets).toEqual(["0", "1"]);
  await page.getByText("Manage saved products (2)", { exact: true }).click();
  await page.getByRole("button", { name: "View Second profile", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText("0 USD");
  await page.screenshot({ path: "test-results/profile-details-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "View Second profile", exact: true })).toBeFocused();
});

test("account change clears saved run and profile before mounting new account", async ({ page }) => {
  let account = "first";
  await page.route("**/api/v1/**", route => route.fulfill({ json: route.request().url().includes("/auth/me") ? { id: account, email: `${account}@example.test` } : { items: [{ ...demoProduct, id: account, name: `${account} profile` }], total: 1 } }));
  await page.goto("/products");
  await expect(page.getByLabel("Product name")).toHaveValue("first profile");
  await page.evaluate(() => localStorage.setItem("run_id", "first-run"));
  account = "second";
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByLabel("Product name")).toHaveValue("second profile");
  expect(await page.evaluate(() => localStorage.getItem("run_id"))).toBeNull();
});
