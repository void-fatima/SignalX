import { createServer, type Server } from "node:http";
import { test, expect } from "@playwright/test";
import { telegramLead as lead } from "./fixtures/telegram";

test.describe("offline session bridge", () => {
  test.describe.configure({ mode: "serial" });
  let server: Server;
  const calls: { authorization: string | undefined; method: string | undefined; path: string | undefined; body: string }[] = [];
  let status = 200;
  test.beforeAll(async () => {
    server = createServer(async (request, response) => {
      let body = "";
      for await (const chunk of request) body += chunk.toString();
      calls.push({ authorization: request.headers.authorization, method: request.method, path: request.url, body });
      response.writeHead(status, { "Content-Type": "application/json" });
      response.end(JSON.stringify(status === 200 ? lead : { error: { code: "telegram_delivery_failed", message: "Synthetic failure", details: [] } }));
    });
    await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(3201, "127.0.0.1", resolve); });
  });
  test.afterAll(async () => { if (server) await new Promise<void>(resolve => server.close(() => resolve())); });
  test.beforeEach(() => { calls.length = 0; status = 200; });

  test("HttpOnly backend session is forwarded as Bearer with the exact approved body", async ({ playwright }) => {
    const context = await playwright.request.newContext({ baseURL: "http://localhost:3100", extraHTTPHeaders: { Cookie: "singnalx_session=offline-test-session", Origin: "http://localhost:3100" } });
    try {
      const exact = "  Hello 👋\nسلام  ";
      const response = await context.post(`/api/v1/leads/${lead.id}/telegram/reply`, { data: { text: exact } });
      expect(response.status()).toBe(200);
      expect(calls).toHaveLength(1);
      expect(calls[0]).toEqual({ authorization: "Bearer offline-test-session", method: "POST", path: `/api/v1/leads/${lead.id}/telegram/reply`, body: JSON.stringify({ text: exact }) });
      expect(response.headers()["cache-control"]).toBe("no-store");
      expect(await response.text()).not.toContain("offline-test-session");
    } finally { await context.dispose(); }
  });

  test("server preserves the backend error envelope and makes only one POST", async ({ playwright }) => {
    status = 502;
    const context = await playwright.request.newContext({ baseURL: "http://localhost:3100", extraHTTPHeaders: { Cookie: "singnalx_session=offline-test-session", Origin: "http://localhost:3100" } });
    try {
      const response = await context.post(`/api/v1/leads/${lead.id}/telegram/reply`, { data: { text: "Reviewed text" } });
      expect(response.status()).toBe(502);
      expect((await response.json()).error.code).toBe("telegram_delivery_failed");
      expect(calls).toHaveLength(1);
    } finally { await context.dispose(); }
  });
});
