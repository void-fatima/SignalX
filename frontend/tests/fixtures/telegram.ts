import type { Page } from "@playwright/test";
import fixture from "./telegram-lead.json";
import type { TelegramLead } from "../../lib/telegram";
export const telegramLead = fixture as TelegramLead;
export async function mockTelegram(page: Page, value: TelegramLead = telegramLead) {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/integrations/telegram/leads")) return route.fulfill({ json: { items: [value], total: 1, limit: 20, offset: 0 } });
    if (path.endsWith("/telegram")) return route.fulfill({ json: value });
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "owner", email: "owner@example.test" } : { items: [], total: 0 } });
  });
}
