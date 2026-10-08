import { test, expect } from "@playwright/test";
import { demoProduct } from "../lib/product-profile";
import type { Product, ProductInput } from "../lib/api";
const realProduct: Product = { ...demoProduct, id: "a310f932-0000-4000-8000-000000000001" };

test("demo preview follows edits, cancellation and explicitly local saves", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/v1/**", route => { requests++; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/products?demo=1");
  await expect(page.getByLabel("Product name")).toHaveValue("Backend Academy");
  await page.getByLabel("Product name").fill("محصول آزمایشی");
  await expect(page.locator(".product-preview h2")).toHaveText("محصول آزمایشی");
  await expect(page.getByLabel("Selected product")).toBeDisabled();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Product name")).toHaveValue("Backend Academy");
  await page.getByLabel("Best fit", { exact: true }).fill("First group\n\n Second group ");
  await expect(page.locator(".product-preview li").filter({ hasText: "Second group" })).toBeVisible();
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page.getByRole("status")).toContainText("Saved locally · demo. Changes reset on reload.");
  expect(await page.evaluate(() => localStorage.getItem("product_id"))).toBeNull();
  expect(requests).toBe(0);
});

test("invalid product fields show focused errors before any write", async ({ page }) => {
  await page.goto("/products?demo=1");
  await page.getByLabel("Product name").fill(" ");
  await page.getByLabel("Price (optional)").fill("-5");
  await page.getByLabel("Currency", { exact: true }).fill("US");
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page.getByLabel("Product name")).toBeFocused();
  await expect(page.getByText("Product name is required.")).toBeVisible();
  await expect(page.getByText(/Use a nonnegative price/)).toBeVisible();
  await expect(page.getByText(/Use a three-letter currency code/)).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("real product PATCH preserves typed lists, zero price and persistence feedback", async ({ page }) => {
  const writes: { method: string; body: ProductInput }[] = [];
  await page.route("**/api/v1/**", route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "PATCH") {
      const body = request.postDataJSON() as ProductInput;
      writes.push({ method: request.method(), body });
      return route.fulfill({ json: { ...realProduct, ...body } });
    }
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "user-1", email: "owner@example.test" } : { items: [realProduct], total: 1 } });
  });
  await page.goto("/products");
  await expect(page.getByLabel("Product name")).toHaveValue(realProduct.name);
  await page.getByLabel("Problems solved").fill(" First problem \n\nSecond problem ");
  await page.getByLabel("Price (optional)").fill("0");
  await page.getByLabel("Currency", { exact: true }).fill("eur");
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page.getByRole("status")).toHaveText("Product saved.");
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toMatchObject({ problems_solved: ["First problem", "Second problem"], price: "0", currency: "EUR" });
  expect(await page.evaluate(() => localStorage.getItem("product_id"))).toBe(realProduct.id);
  await expect(page.getByRole("button", { name: "Save product" })).toBeDisabled();
});

test("empty API results create a product only after successful POST", async ({ page }) => {
  let body: ProductInput | undefined;
  await page.route("**/api/v1/**", route => {
    if (route.request().url().endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "owner@example.test" } });
    if (route.request().method() === "POST") { body = route.request().postDataJSON(); return route.fulfill({ status: 201, json: { ...realProduct, ...body } }); }
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/products");
  await expect(page.getByText(/No saved products yet/)).toBeVisible();
  await expect(page.locator(".saved-count strong")).toHaveText("00");
  await expect(page.getByLabel("Product name")).toHaveValue("");
  await page.getByLabel("Product name").fill("New profile");
  await page.getByLabel("Description", { exact: true }).fill("Profile description");
  await page.getByLabel("Target customer").fill("Profile customer");
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page.getByRole("status")).toHaveText("Product saved.");
  expect(body?.price).toBeNull();
  await expect(page.locator(".saved-count strong")).toHaveText("01");
});

test("failed saves keep unsaved edits and never report success", async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    if (route.request().url().endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "owner@example.test" } });
    if (route.request().method() === "PATCH") {
      await new Promise(resolve => setTimeout(resolve, 300));
      return route.fulfill({ status: 503, json: { error: { message: "Save temporarily unavailable." } } });
    }
    return route.fulfill({ json: { items: [realProduct], total: 1 } });
  });
  await page.goto("/products");
  await expect(page.getByLabel("Product name")).toBeEnabled();
  await page.getByLabel("Product name").fill("Unsaved name");
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page.getByLabel("Product name")).toBeDisabled();
  await expect(page.getByRole("alert").filter({ hasText: "Save temporarily unavailable" })).toBeVisible();
  await expect(page.getByLabel("Product name")).toHaveValue("Unsaved name");
  await expect(page.getByRole("button", { name: "Save product" })).toBeEnabled();
  await expect(page.locator(".product-save-state")).toHaveText("Changes not saved");
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("loading and errors do not silently substitute a mock product", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/v1/**", async route => {
    if (route.request().url().endsWith("/auth/me")) return route.fulfill({ json: { id: "user-1", email: "owner@example.test" } });
    if (!route.request().url().includes("/products")) return route.fulfill({ status: 401, json: { error: { message: "Sign in required" } } });
    attempts++;
    await new Promise(resolve => setTimeout(resolve, 300));
    return route.fulfill(attempts === 1 ? { status: 500, json: { error: { message: "Products unavailable" } } } : { json: { items: [realProduct], total: 1 } });
  });
  await page.goto("/products");
  await expect(page.getByText("Loading product profiles…")).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "Products unavailable" })).toBeVisible();
  await expect(page.getByText("MOCK DATA", { exact: true })).toHaveCount(0);
  await expect(page.locator(".saved-count strong")).toHaveText("—");
  await expect(page.getByRole("button", { name: "Save product" })).toBeDisabled();
  await page.getByRole("button", { name: "Retry loading products" }).click();
  await expect(page.getByLabel("Product name")).toBeEnabled();
  await expect(page.locator(".product-preview h2")).toHaveText("Backend Academy");
});

test("workspace search opens the existing filtered opportunity inbox", async ({ page }) => {
  await page.goto("/products?demo=1");
  await page.getByRole("searchbox", { name: "Search workspace conversations" }).fill("Navid");
  await page.getByRole("searchbox", { name: "Search workspace conversations" }).press("Enter");
  await expect(page).toHaveURL(/\/leads\?q=Navid&demo=1$/);
  await expect(page.locator(".queue-row")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Open signal analysis for Navid" })).toBeVisible();
});

test("saved product selection protects edits and offers a separate new draft", async ({ page }) => {
  const second = { ...realProduct, id: "a310f932-0000-4000-8000-000000000002", name: "Second product", description: "Another saved description" };
  await page.route("**/api/v1/**", route => route.fulfill({ json: route.request().url().endsWith("/auth/me") ? { id: "user-1", email: "owner@example.test" } : { items: [realProduct, second], total: 2 } }));
  await page.goto("/products");
  const selector = page.getByLabel("Selected product");
  await expect(selector).toBeEnabled();
  await selector.selectOption(second.id);
  await expect(page.getByLabel("Description", { exact: true })).toHaveValue(second.description);
  expect(await page.evaluate(() => localStorage.getItem("product_id"))).toBe(second.id);
  await page.getByLabel("Product name").fill("Changed second product");
  await expect(selector).toBeDisabled();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Product name")).toHaveValue(second.name);
  await selector.selectOption("");
  await expect(page.getByText("NEW DRAFT", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save product" })).toBeEnabled();
  await expect(page.locator(".saved-count strong")).toHaveText("02");
});

for (const viewport of [{ width: 1285, height: 866 }, { width: 900, height: 700 }, { width: 390, height: 844 }]) {
  test(`product editor and preview remain usable at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/products?demo=1");
    await expect(page.locator(".product-preview h2")).toHaveText("Backend Academy");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (viewport.width < 700) {
      await page.getByRole("button", { name: "Toggle workspace navigation" }).click();
      await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Products" })).toHaveAttribute("aria-current", "page");
      await page.getByRole("button", { name: "Toggle workspace navigation" }).click();
    }
    await page.getByLabel("Description", { exact: true }).fill("Editable preview description");
    await expect(page.locator(".preview-description")).toHaveText("Editable preview description");
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await page.reload();
    await expect(page.getByLabel("Product name")).toBeEnabled();
    await page.screenshot({ path: `test-results/product-${viewport.width}.png`, fullPage: true });
  });
}
