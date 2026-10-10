import { test, expect, type Page } from "@playwright/test";
const product = { id: "product-1", name: "LedgerFlow", description: "Accounting tools", target_customer: "Finance teams", problems_solved: [], best_fit: [], not_fit: [], price: null, currency: "USD", created_at: "2026-10-10T00:00:00Z" };
const result = { source: "brave", source_id: "source-1", title: "Acme finance", url: "https://acme.example.com/finance", excerpt: "A public finance operations page.", location: "", signal: "not_evaluated", explanation: "Source match only; buying intent has not been verified." };
const search = { id: "search-1", product_id: product.id, source: "brave", status: "completed", results: [result], cached: false, request_count: 1, estimated_cost_usd: null, cost_status: "unknown", error_code: null, error: null, created_at: product.created_at };
async function setup(page: Page, options: { configured?: boolean; failOnce?: boolean; unsafe?: boolean } = {}) {
  const writes: { path: string; body: any; key: string | undefined }[] = [];
  let saved: any[] = [];
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { id: "owner", email: "owner@example.test" } });
    if (path.endsWith("/products")) return route.fulfill({ json: { items: [product], total: 1, limit: 100, offset: 0 } });
    if (path.endsWith("/discovery/sources")) return route.fulfill({ json: { items: ["brave", "greenhouse", "lever", "places"].map(source => ({ source, configured: source === "places" ? false : options.configured !== false, message: source === "places" ? "Configure Google Places API credentials and review ID-only storage." : options.configured === false ? "Configuration required. No results are fabricated." : "Configured public source." })) } });
    if (request.method() === "POST") {
      writes.push({ path, body: request.postDataJSON(), key: request.headers()["idempotency-key"] });
      if (path.endsWith("/searches")) {
        if (options.failOnce && writes.length === 1) return route.abort("failed");
        return route.fulfill({ json: { ...search, source: request.postDataJSON().source, results: options.unsafe ? [{ ...result, title: "<script>bad</script>", excerpt: "<img src=x onerror=bad>", url: "javascript:alert(1)" }] : [result] } });
      }
      if (path.endsWith("/prospects")) { saved = [{ ...result, id: "prospect-1", product_id: product.id, search_id: search.id, qualification_status: "not_requested", qualification_usage: [], qualification_error: null, created_at: product.created_at }]; return route.fulfill({ json: saved }); }
      throw new Error(`Unexpected paid analysis or sending path: ${path}`);
    }
    if (path.endsWith("/searches")) return route.fulfill({ json: [] });
    if (path.endsWith("/prospects")) return route.fulfill({ json: saved });
    return route.fulfill({ status: 404, json: {} });
  });
  return writes;
}
for (const width of [1440, 390]) test(`explicit search preview and save need no CSV or AI at ${width}px`, async ({ page }) => {
  const writes = await setup(page);
  await page.setViewportSize({ width, height: 844 });
  await page.goto("/discover");
  await expect(page.getByRole("heading", { name: "Discover Leads", exact: true })).toBeVisible();
  await expect(page.getByLabel("Product", { exact: true })).toHaveValue(product.id);
  expect(writes).toHaveLength(0);
  await expect(page.getByLabel("Search source")).toContainText("Web search \u00b7 Brave");
  await expect(page.locator(".discovery-page")).not.toContainText("\u00c2");
  await page.getByLabel("Keywords", { exact: true }).fill("finance operations");
  await page.getByRole("button", { name: "Search prospects" }).click();
  await expect(page.getByRole("region", { name: "Discovery results" })).toContainText("Acme finance");
  await expect(page.getByRole("region", { name: "Discovery results" })).toContainText("Not AI evaluated");
  await expect(page.getByRole("link", { name: "Open original source" })).toHaveAttribute("href", result.url);
  expect(writes).toHaveLength(1); expect(writes[0].body.limit).toBe(10); expect(writes[0].body.product_id).toBe(product.id);
  await page.getByRole("checkbox", { name: "Select Acme finance" }).check();
  await page.getByRole("button", { name: "Save selected prospects" }).click();
  await expect(page.getByRole("region", { name: "Saved prospects" })).toContainText("AI evaluation not requested");
  expect(writes.map(w => w.path)).toEqual(["/api/v1/discovery/searches", "/api/v1/discovery/prospects"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `test-results/discovery-${width}.png`, fullPage: true });
});

test("missing configuration is truthful and job sources require a company board", async ({ page }) => {
  const writes = await setup(page, { configured: false });
  await page.goto("/discover");
  await expect(page.getByRole("button", { name: "Search prospects" })).toBeDisabled();
  await expect(page.locator(".discovery-form")).toContainText("Configuration required");
  await page.getByLabel("Search source").selectOption("greenhouse");
  await expect(page.getByLabel("Company board slug")).toHaveAttribute("required", "");
  await expect(page.locator(".discovery-form")).toContainText("not universal job-board search");
  await page.getByLabel("Search source").selectOption("places");
  await expect(page.getByLabel("Location (required)")).toHaveAttribute("required", "");
  expect(writes).toHaveLength(0);
});

test("uncertain search is replayed explicitly with the same key after reload", async ({ page }) => {
  const writes = await setup(page, { failOnce: true });
  await page.goto("/discover");
  await page.getByLabel("Keywords", { exact: true }).fill("finance");
  await page.getByRole("button", { name: "Search prospects" }).click();
  await expect(page.getByRole("button", { name: "Check previous search" })).toBeVisible();
  expect(writes).toHaveLength(1);
  await page.reload();
  await page.getByRole("button", { name: "Check previous search" }).click();
  await expect(page.getByRole("region", { name: "Discovery results" })).toBeVisible();
  expect(writes).toHaveLength(2); expect(writes[0].key).toBe(writes[1].key);
});

test("untrusted snippets are escaped and unsafe links cannot be saved", async ({ page }) => {
  await setup(page, { unsafe: true });
  await page.goto("/discover");
  await page.getByLabel("Keywords", { exact: true }).fill("finance");
  await page.getByRole("button", { name: "Search prospects" }).click();
  await expect(page.getByRole("region", { name: "Discovery results" })).toContainText("<img src=x onerror=bad>");
  await expect(page.getByRole("link", { name: "Open original source" })).toHaveCount(0);
  await expect(page.getByRole("checkbox")).toBeDisabled();
  expect(await page.evaluate(() => "bad" in window)).toBe(false);
});

test("demo does not search or invent results", async ({ page }) => {
  const writes = await setup(page);
  await page.goto("/discover?demo=1");
  await expect(page.getByText("Demo mode does not search or fabricate results.", { exact: false })).toBeVisible();
  expect(writes).toHaveLength(0);
});


test("paid evaluation requires its own action and preserves unknown usage", async ({ page }) => {
  const writes = await setup(page);
  await page.route("**/api/v1/discovery/prospects/prospect-1/qualify", async route => {
    writes.push({ path: new URL(route.request().url()).pathname, body: null, key: route.request().headers()["idempotency-key"] });
    await route.fulfill({ json: { ...result, id: "prospect-1", product_id: product.id, search_id: search.id, qualification_status: "completed", signal: "possible_need", explanation: "Possible need; buying intent is unverified.", qualification_error: null, created_at: product.created_at, qualification_usage: [{ stage: "qualification", attempt_no: 1, provider_mode: "real", model: "offline-model", input_tokens: 120, output_tokens: 40, estimated_cost: null, cost_status: "unknown", price_version: null, latency_ms: 20, outcome: "success" }] } });
  });
  await page.goto("/discover");
  await page.getByLabel("Keywords", { exact: true }).fill("finance");
  await page.getByRole("button", { name: "Search prospects" }).click();
  await page.getByRole("checkbox", { name: "Select Acme finance" }).check();
  await page.getByRole("button", { name: "Save selected prospects" }).click();
  const evaluate = page.getByRole("button", { name: "Evaluate this prospect with AvalAI (paid)" });
  await expect(evaluate).toBeVisible(); expect(writes).toHaveLength(2);
  await evaluate.click();
  await expect(page.getByRole("region", { name: "Saved prospects" })).toContainText("completed \u00b7 possible need");
  await expect(page.getByRole("region", { name: "Saved prospects" })).toContainText("estimated USD unknown");
  expect(writes).toHaveLength(3); expect(writes[2].key).toBeTruthy();
  await expect(evaluate).toHaveCount(0);
  expect(writes.filter(write => /analysis|telegram|send/.test(write.path))).toHaveLength(0);
});
