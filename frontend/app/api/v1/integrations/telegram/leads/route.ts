import { NextRequest } from "next/server";
import { telegramProxy } from "@/lib/telegram-proxy";
export function GET(request: NextRequest) {
  const offset = Math.max(0, Number.parseInt(request.nextUrl.searchParams.get("offset") || "0", 10) || 0);
  return telegramProxy(request, `/integrations/telegram/leads?limit=20&offset=${offset}`);
}
