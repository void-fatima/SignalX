import "server-only";
import { NextRequest, NextResponse } from "next/server";

function error(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, details: [] } }, { status, headers: { "Cache-Control": "no-store" } });
}
/** Translate the existing HttpOnly backend session; never expose a token to JS. */
export async function telegramProxy(request: NextRequest, path: string) {
  if (request.method !== "GET") return error(405, "method_not_allowed", "This operation is not available.");
  const token = request.cookies.get(process.env.BACKEND_SESSION_COOKIE || "singnalx_session")?.value;
  if (!token) return error(401, "authentication_required", "Sign in to access Telegram leads. The backend session cookie must be available on the app host.");
  const base = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  try {
    const response = await fetch(`${base.replace(/\/$/, "")}${path}`, {
      headers: { Authorization: `Bearer ${token}` }, cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(30_000),
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return error(502, "telegram_backend_unavailable", "Telegram backend could not be reached or returned an unreadable response.");
  }
}
