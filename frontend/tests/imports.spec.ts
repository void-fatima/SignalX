import { test, expect } from "@playwright/test";
import { demoProduct } from "../lib/product-profile";
import { demoRun } from "../lib/demo-inbox";
import { fileIssue, validateCsv, requiredColumns } from "../lib/csv-validation";
const header = requiredColumns.join(",");
const valid = `${header}\n1,c1,Alex,"Looking for a backend course, with projects",2026-10-07T09:10:00+03:30`;
const upload = (name: string, text: string) => ({ name, mimeType: "text/csv", buffer: Buffer.from(text) });

test("CSV preflight supports BOM escaped quotes and multiline messages", () => {
  const result = validateCsv(`\uFEFF${header}\r\n1,c1,Alex,"A \"\"course\"\" with commas,\nand projects",2026-10-07T09:10:00Z\r\n`);
  expect(result.issues).toEqual([]); expect(result.validCount).toBe(1);
  expect(result.messages[0].content).toBe('A "course" with commas,\nand projects');
  expect(fileIssue("data.txt", 5)?.issue).toContain("Invalid file type");
  expect(fileIssue("data.csv", 5 * 1024 * 1024 + 1)?.issue).toContain("5 MB");
  expect(fileIssue("data.csv", 0)?.issue).toContain("empty");
  expect(validateCsv(header).issues[0].issue).toContain("No messages");
  expect(validateCsv(`${header}\n1,c1,A,"unclosed`).issues[0].issue).toContain("closing quote");
  expect(validateCsv(`${header}\n` + Array.from({ length: 501 }, (_, i) => `${i},c1,A,B,2026-10-07T09:10:00Z`).join("\n")).issues[0].issue).toContain("500");
});

test("reference validation blocks analysis until a genuine replacement passes", async ({ page }) => {
  await page.setViewportSize({ width: 1285, height: 900 });
  let calls = 0;
  await page.route("**/api/v1/**", route => { calls++; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/imports?demo=1");
  await expect(page.getByText("20 valid rows")).toBeVisible();
  await expect(page.getByText("Fix 2 rows to continue.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start analysis", exact: true })).toBeDisabled();
  await page.screenshot({ path: "test-results/imports-desktop.png", fullPage: true });
  await page.getByLabel("CSV file", { exact: true }).setInputFiles(upload("replacement.csv", valid));
  await expect(page.getByText("All 1 rows passed local validation.")).toBeVisible();
  expect(calls).toBe(0);
  await page.getByRole("button", { name: "Preview analysis", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/demo-import\?demo=1/);
});

test("replacement reports missing columns empty content timezone and encoding", async ({ page }) => {
  await page.goto("/imports?demo=1");
  const file = page.getByLabel("CSV file", { exact: true });
  await file.setInputFiles(upload("bad.txt", valid)); await expect(page.getByText("Invalid file type.")).toBeVisible();
  await file.setInputFiles(upload("bad.csv", "author,content\nAlex,Hello")); await expect(page.getByText(/Missing columns:/)).toBeVisible();
  await file.setInputFiles(upload("bad.csv", `${header}\n1,c1,Alex,,2026-10-07T09:10:00`));
  await expect(page.getByText("Message text is empty.")).toBeVisible(); await expect(page.getByText("Timezone is missing.")).toBeVisible();
  await file.setInputFiles({ name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from([0xff, 0xfe]) }); await expect(page.getByText("File is not valid UTF-8.")).toBeVisible();
  await file.setInputFiles(upload("empty.csv", "")); await expect(page.getByText("The file is empty.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start analysis", exact: true })).toBeDisabled();
});

test("connected import starts once validated and retries with the same run key", async ({ page }) => {
  let imports = 0; const keys: string[] = [];
  await page.route("**/api/v1/**", route => {
    const request = route.request(), url = new URL(request.url());
    if (url.pathname.endsWith("/imports")) { imports++; return route.fulfill({ json: { batch: { id: "batch-1" }, count: 1, duplicate: false, warnings: [] } }); }
    if (url.pathname.endsWith("/analysis/runs")) { keys.push(request.headers()["idempotency-key"]); return keys.length === 1 ? route.fulfill({ status: 503, json: { error: { message: "Worker unavailable. Try again." } } }) : route.fulfill({ json: { ...demoRun, id: "run-1", status: "queued", total_count: 1 } }); }
    if (url.pathname.includes("/analysis/runs/")) return route.fulfill({ json: { ...demoRun, id: "run-1" } });
    return route.fulfill({ json: url.pathname.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [demoProduct] } });
  });
  await page.goto("/imports");
  await expect(page.getByLabel("Product", { exact: true })).toHaveValue(demoProduct.id);
  await page.getByLabel("CSV file", { exact: true }).setInputFiles(upload("valid.csv", valid));
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();
  await expect(page.locator(".workflow-error")).toContainText("Worker unavailable");
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/run-1/);
  expect(imports).toBe(1); expect(keys).toHaveLength(2); expect(keys[0]).toBe(keys[1]);
});

test("mobile validation preserves readable scrollable tables and actions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/imports?demo=1");
  await expect(page.getByText("Fix 2 rows to continue.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole("button", { name: "Replace CSV", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/imports-mobile.png", fullPage: true });
});
