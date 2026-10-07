import { test, expect } from "@playwright/test";

const user = { id: "ui-test-user", email: "person@example.test", created_at: "2026-10-07T00:00:00Z" };

test("sign-in validation and password visibility remain accessible", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/v1/auth/**", route => { requests++; return route.fulfill({ status: 500, json: { error: { message: "Should not be called" } } }); });
  await page.goto("/login?demo=1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Email", { exact: true })).toBeFocused();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("demonstration-only");
  await page.getByRole("button", { name: "Show password", exact: true }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide password", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("No account was signed in");
  expect(requests).toBe(0);
});

test("sign in navigates only after the backend verifies a cookie session", async ({ page }) => {
  const methods: string[] = [];
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    methods.push(`${route.request().method()} ${path}`);
    return route.fulfill({ json: path.endsWith("/auth/login") ? { user, expires_at: "2026-10-08T00:00:00Z" } : path.endsWith("/auth/me") ? user : { items: [], total: 0, limit: 100, offset: 0 } });
  });
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("demonstration-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/products$/);
  expect(methods).toContain("POST /api/v1/auth/login");
  expect(methods).toContain("GET /api/v1/auth/me");
  expect(await page.evaluate(() => Object.keys(localStorage).some(key => /password|token|session/i.test(key)))).toBe(false);
});

test("authentication errors remain errors and preserve an editable form", async ({ page }) => {
  await page.route("**/api/v1/auth/login", route => route.fulfill({ status: 401, json: { error: { message: "Email or password is incorrect" } } }));
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("demonstration-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await expect(page).toHaveURL(/\/login$/);
});

for (const viewport of [{ width: 1705, height: 1152 }, { width: 390, height: 844 }]) {
  test(`sign-in reference layout at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/login?demo=1");
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator(".sidebar")).toHaveCount(0);
    await page.screenshot({ path: `test-results/login-${viewport.width}.png`, fullPage: true });
    await page.getByRole("link", { name: "Create an account" }).click();
    await expect(page).toHaveURL(/\/register\?demo=1$/);
  });
}
