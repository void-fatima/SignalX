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

test("registration checks password confirmation without posting invalid input", async ({ page }) => {
  let posts = 0;
  await page.route("**/api/v1/auth/register", route => { posts++; return route.fulfill({ status: 201, json: user }); });
  await page.goto("/register");
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("demonstration-only");
  await page.getByLabel("Confirm password", { exact: true }).fill("different-password");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByText("Passwords must match.")).toBeVisible();
  await expect(page.getByLabel("Confirm password", { exact: true })).toBeFocused();
  expect(posts).toBe(0);
  await page.getByRole("button", { name: "Show confirm password", exact: true }).click();
  await expect(page.getByLabel("Confirm password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByLabel("Confirm password", { exact: true }).fill("demonstration-only");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Account created. Sign in to continue.");
  expect(posts).toBe(1);
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  await expect(page).toHaveURL(/\/register$/);
});

test("duplicate accounts show the backend error without claiming success", async ({ page }) => {
  await page.route("**/api/v1/auth/register", route => route.fulfill({ status: 409, json: { error: { message: "An account with this email already exists" } } }));
  await page.goto("/register");
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("demonstration-only");
  await page.getByLabel("Confirm password", { exact: true }).fill("demonstration-only");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "already exists" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Account created", exact: true })).toHaveCount(0);
});

for (const viewport of [{ width: 1285, height: 866 }, { width: 390, height: 700 }, { width: 900, height: 600 }]) {
  test(`account creation remains usable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/register?demo=1");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Create account", exact: true }).scrollIntoViewIfNeeded();
    await expect(page.getByRole("button", { name: "Create account", exact: true })).toBeInViewport();
    await page.screenshot({ path: `test-results/signup-${viewport.width}x${viewport.height}.png`, fullPage: true });
    await page.getByRole("link", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/login\?demo=1$/);
  });
}
