import { test, expect } from "@playwright/test";
const key = "signalx:preferences:v1";

test("preferences are staged then persisted and applied to messages after reload", async ({ page }) => {
  await page.goto("/settings?demo=1");
  await page.getByRole("radio", { name: "Light", exact: true }).focus(); await page.keyboard.press("Space");
  await page.getByRole("radio", { name: "Compact", exact: true }).focus(); await page.keyboard.press("Space");
  await page.getByLabel("Message direction", { exact: true }).selectOption("ltr");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  await expect(page.getByRole("status")).toContainText("this browser");
  await page.reload();
  await expect(page.getByRole("radio", { name: "Light", exact: true })).toBeChecked();
  await page.screenshot({ path: "test-results/settings-light.png", fullPage: true });
  await page.goto("/leads/demo-lead-1?demo=1");
  await expect(page.locator(".source-quote")).toHaveAttribute("dir", "ltr");
  await expect(page.getByLabel("Reply draft")).toHaveAttribute("dir", "ltr");
  await page.goto("/settings?demo=1");
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await page.evaluate(key => localStorage.getItem(key), key)).toBeNull();
});

test("system theme follows device changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/settings?demo=1");
  await page.getByRole("radio", { name: "System", exact: true }).focus(); await page.keyboard.press("Space");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("light preferences keep existing product and sign-in surfaces readable", async ({ page }) => {
  await page.goto("/settings?demo=1");
  await page.locator(".theme-choice").filter({ has: page.getByRole("radio", { name: "Light", exact: true }) }).click();
  await page.getByRole("button", { name: "Save preferences" }).click();
  await page.getByRole("link", { name: "Products", exact: true }).click();
  await expect(page.locator(".product-preview")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.locator(".product-preview h2")).toHaveCSS("color", "rgb(28, 35, 51)");
  await page.goto("/login?demo=1");
  await expect(page.locator(".auth-layout")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toHaveCSS("color", "rgb(28, 35, 51)");
});

test("invalid stored data and denied storage never claim success", async ({ page }) => {
  await page.addInitScript(key => {
    localStorage.setItem(key, "broken");
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (name, value) { if (name === key) throw new Error("blocked"); original.call(this, name, value); };
  }, key);
  await page.goto("/settings?demo=1");
  await expect(page.locator(".preferences-card").getByRole("alert")).toContainText("could not be read");
  await page.getByRole("radio", { name: "Light", exact: true }).focus(); await page.keyboard.press("Space");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.locator(".preferences-card").getByRole("alert")).toContainText("were not saved");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("demo sign out exits the demo without calling auth", async ({ page }) => {
  let posts = 0;
  await page.route("**/api/v1/**", route => { if (route.request().method() === "POST") posts++; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/settings?demo=1");
  await expect(page.getByLabel("Account summary")).toContainText("no live session");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login\?demo=1$/);
  expect(posts).toBe(0);
});

test("server sign out failure preserves the account and retry ends the session", async ({ page }) => {
  let fail = true;
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/auth/logout")) return route.fulfill({ status: fail ? 503 : 204, ...(fail ? { json: { error: { message: "Unavailable" } } } : {}) });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/settings");
  await expect(page.getByLabel("Account summary")).toContainText("Signed in");
  await page.getByLabel("Account summary").getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Account summary").getByRole("alert")).toContainText("Sign out failed");
  await expect(page).toHaveURL(/\/settings$/);
  fail = false;
  await page.getByLabel("Account summary").getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
});

for (const width of [1285, 390]) test(`settings matches its responsive shell at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: width === 390 ? 844 : 841 });
  await page.goto("/settings?demo=1");
  await expect(page.getByRole("heading", { name: "Workspace settings" })).toBeVisible();
  await expect(page.locator(".skip-link")).not.toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator(".sidebar-settings")).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "Save preferences" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Save preferences" })).toBeInViewport();
  await expect(page.locator(".skip-link")).not.toBeInViewport();
  await page.screenshot({ path: `test-results/settings-${width}.png`, fullPage: true });
});
