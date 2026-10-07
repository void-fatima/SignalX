import { test, expect } from "@playwright/test";
import { demoDetails, demoRun } from "../lib/demo-inbox";

test("reference inbox has source evidence and a compact analysis card", async ({ page }) => {
  await page.goto("/leads?demo=1");
  await expect(page.getByRole("heading", { name: "Opportunity inbox" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open signal analysis for Mina" })).toBeVisible();
  await expect(page.locator(".source-quote mark")).toHaveCount(2);
  await expect(page.locator(".queue-row .avatar").first()).toHaveCSS("border-radius", "50%");
  await expect(page.locator(".source-quote")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.screenshot({ path: "test-results/inbox-desktop.png", fullPage: true });
});

test("analysis dialog is centered in the full viewport and uses Mina's data", async ({ page }) => {
  await page.goto("/leads?demo=1");
  const opener = page.getByRole("button", { name: "Open signal analysis for Mina" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Signal analysis" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".dialog-score-value strong")).toHaveText("84");
  await expect(dialog.getByText("Strong product fit", { exact: true })).toBeVisible();
  await expect(dialog.locator(".dialog-evidence blockquote")).toHaveText(["دوره بک‌اند", "پروژه واقعی"]);
  await expect(dialog.getByRole("meter", { name: "Product fit" })).toHaveAttribute("aria-valuenow", "0.9");
  const bounds = (await dialog.boundingBox())!;
  expect(Math.abs(bounds.x + bounds.width / 2 - 864)).toBeLessThan(2);
  expect(Math.abs(bounds.y + bounds.height / 2 - 585)).toBeLessThan(2);
  await page.screenshot({ path: "test-results/dialog-desktop.png", fullPage: true });
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("");
});

test("selection changes dialog metadata score and evidence together", async ({ page }) => {
  await page.goto("/leads?demo=1");
  await page.getByRole("button", { name: /Navid 48/ }).click();
  await page.getByRole("button", { name: "Open signal analysis for Navid" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.locator(".dialog-score-value strong")).toHaveText("48");
  await expect(dialog.locator(".dialog-source-meta")).toContainText("Navid");
  await expect(dialog.locator(".dialog-evidence blockquote")).toHaveText(["این دوره برای مبتدی‌ها مناسبه؟"]);
  await expect(dialog.getByText("دوره بک‌اند", { exact: true })).toHaveCount(0);
});

test("dialog contains keyboard focus and dismisses only on backdrop or close", async ({ page }) => {
  await page.goto("/leads?demo=1");
  const opener = page.getByRole("button", { name: "Open signal analysis for Mina" });
  await opener.click();
  const dialog = page.getByRole("dialog");
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  await dialog.getByText("Why this surfaced", { exact: true }).click();
  await expect(dialog).toBeVisible();
  await page.mouse.click(10, 10);
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await opener.click();
  await dialog.getByRole("button", { name: "Close signal analysis" }).click();
  await expect(opener).toBeFocused();
});

test("review drafts remain per-lead and approval stays local", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/leads?demo=1");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("textbox", { name: "Reply draft" }).fill("پاسخ بررسی‌شده برای مینا");
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("پاسخ بررسی‌شده برای مینا");
  await page.getByRole("button", { name: "Approve draft" }).click();
  await expect(page.getByRole("button", { name: "Approve draft" })).toBeDisabled();
  await page.getByRole("button", { name: /Alex 79/ }).click();
  await expect(page.getByRole("textbox", { name: "Reply draft" })).not.toHaveValue("پاسخ بررسی‌شده برای مینا");
  await page.getByRole("button", { name: /Mina 84/ }).click();
  await expect(page.getByRole("textbox", { name: "Reply draft" })).toHaveValue("پاسخ بررسی‌شده برای مینا");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Draft rejected locally.");
  await expect(page.getByRole("button", { name: /send/i })).toHaveCount(0);
});

for (const viewport of [{ width: 390, height: 844 }, { width: 900, height: 1000 }]) {
  test(`responsive inbox and scrollable dialog at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/leads?demo=1");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Open signal analysis for Mina" }).click();
    const dialog = page.getByRole("dialog");
    const bounds = (await dialog.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height);
    expect(Math.abs(bounds.x + bounds.width / 2 - viewport.width / 2)).toBeLessThan(2);
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expect(dialog.locator(".dialog-evidence blockquote").first()).toHaveCSS("text-align", "right");
    await dialog.getByRole("button", { name: "Back to conversation" }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `test-results/dialog-${viewport.width}.png` });
    await dialog.getByRole("button", { name: "Back to conversation" }).click();
    await expect(dialog).not.toBeVisible();
  });
}

test("API failures remain errors without a silent demo fallback", async ({ page }) => {
  await page.route("http://localhost:8000/api/v1/**", route => route.fulfill({ status: 500, json: { error: { message: "Backend unavailable" } } }));
  await page.goto("/leads?run_id=live-run");
  await expect(page.getByRole("alert").filter({ hasText: "Backend unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry loading run" })).toBeVisible();
  await expect(page.getByText("MOCK WORKSPACE", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open signal analysis for Mina" })).toHaveCount(0);
});

test("real results use their own signals and unavailable costs", async ({ page }) => {
  const detail = structuredClone(demoDetails["demo-lead-1"]);
  detail.analysis.provider_mode = "real";
  detail.analysis.lead_score = 61;
  detail.analysis.decision = "review";
  detail.analysis.signals!.product_fit = .42;
  detail.message.author = "Live user";
  await page.route("http://localhost:8000/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path.endsWith("/analysis/runs/demo-run-024") ? demoRun : path.endsWith("/leads") ? { items: [detail.analysis], total: 1, limit: 20, offset: 0 } : detail });
  });
  await page.goto("/leads?run_id=demo-run-024");
  await page.getByRole("button", { name: "Open signal analysis for Live user" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("REAL PROVIDER", { exact: true })).toBeVisible();
  await expect(dialog.locator(".dialog-score-value strong")).toHaveText("61");
  await expect(dialog.getByRole("meter", { name: "Product fit" })).toHaveAttribute("aria-valuenow", "0.42");
  await expect(page.locator(".cost")).toContainText("N/A");
});

test("search and score filters select only matching leads", async ({ page }) => {
  await page.goto("/leads?demo=1");
  await page.getByRole("searchbox").fill("Navid");
  await expect(page.locator(".queue-row")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Open signal analysis for Navid" })).toBeVisible();
  await page.getByRole("searchbox").fill("");
  await page.getByRole("button", { name: "Toggle run and score filters" }).click();
  await page.getByLabel("Minimum score").fill("80");
  await expect(page.locator(".queue-row")).toHaveCount(1);
  await page.getByLabel("Minimum score").fill("100");
  await expect(page.getByText("No opportunities match these filters.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Open signal analysis/ })).toHaveCount(0);
});

test("empty unconfigured workspace requires an explicit choice to enter demo", async ({ page }) => {
  await page.goto("/leads");
  await expect(page.getByText("Import messages to start an analysis.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore the mock workspace ↗" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Open signal analysis/ })).toHaveCount(0);
});

test("loading source state gives way to an honest failed-analysis dialog", async ({ page }) => {
  const detail = structuredClone(demoDetails["demo-lead-1"]);
  detail.analysis.status = "failed";
  detail.analysis.provider_mode = "real";
  detail.analysis.lead_score = null;
  detail.analysis.decision = null;
  detail.analysis.signals = null;
  detail.analysis.evidence = [];
  detail.analysis.reason = "Provider request failed.";
  await page.route("http://localhost:8000/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/leads/")) await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({ json: path.endsWith("/analysis/runs/demo-run-024") ? demoRun : path.endsWith("/leads") ? { items: [detail.analysis], total: 1, limit: 20, offset: 0 } : detail });
  });
  await page.goto("/leads?run_id=demo-run-024");
  await expect(page.getByText("Gathering the conversation")).toBeVisible();
  await page.getByRole("button", { name: "Open signal analysis for Mina" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.locator(".dialog-score-value strong")).toHaveText("—");
  await expect(dialog.getByRole("meter")).toHaveCount(0);
  await expect(dialog.getByText("Signals are unavailable for this analysis.")).toBeVisible();
  await expect(dialog.locator(".dialog-evidence blockquote")).toHaveCount(0);
});

test("account shell shares the brand and remains an honest integration shell", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator(".brand-large img")).toBeVisible();
  await expect(page.getByLabel("Email")).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("not connected yet");
});
