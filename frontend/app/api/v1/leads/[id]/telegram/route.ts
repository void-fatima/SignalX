import { NextRequest } from "next/server";
import { telegramProxy } from "@/lib/telegram-proxy";
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return telegramProxy(request, `/leads/${encodeURIComponent(id)}/telegram`);
}
