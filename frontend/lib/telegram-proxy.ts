import "server-only";
import { NextRequest, NextResponse } from "next/server";

function error(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, details: [] } }, { status, headers: { "Cache-Control": "no-store" } });
}
/** Translate the existing HttpOnly backend session; never expose a token to JS. */
export async function telegramProxy(request: NextRequest, path: string, operation: "read" | "suggest" | "send" = "read") {
  if (request.method !== (operation === "read" ? "GET" : "POST")) return error(405, "method_not_allowed", "This operation is not available.");
  let payload: string | undefined;
  if (operation !== "read") {
    const origin = request.headers.get("origin");
    if (!origin || origin !== (process.env.APP_ORIGIN || request.nextUrl.origin)) return error(403, "invalid_origin", "Request origin is not allowed.");
    try {
      const raw = await request.text();
      if (raw.length > 16_000) return error(413, "payload_too_large", "Reply request is too large.");
      const body = JSON.parse(raw);
      if (operation === "suggest") {
        if (typeof body?.regenerate !== "boolean" || Object.keys(body).length !== 1) return error(422, "invalid_draft_request", "Choose an explicit draft generation action.");
        payload = JSON.stringify({ regenerate: body.regenerate });
      } else {
        if (typeof body?.text !== "string" || !body.text.trim() || Array.from(body.text).length > 4000 || Object.keys(body).length !== 1) return error(422, "invalid_reply", "Review a nonblank reply of at most 4000 characters.");
        payload = JSON.stringify({ text: body.text }); // Preserve the exact approved text.
      }
    } catch { return error(422, "invalid_request", "The request body is invalid."); }
  }
  const token = request.cookies.get(process.env.BACKEND_SESSION_COOKIE || "singnalx_session")?.value;
  if (!token) return error(401, "authentication_required", "Sign in to access Telegram leads. The backend session cookie must be available on the app host.");
  const base = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  try {
    const response = await fetch(`${base.replace(/\/$/, "")}${path}`, {
      method: request.method, body: payload,
      headers: { Authorization: `Bearer ${token}`, ...(payload ? { "Content-Type": "application/json" } : {}) }, cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(operation === "read" ? 30_000 : 120_000),
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return error(502, "telegram_backend_unavailable", "Telegram backend could not be reached or returned an unreadable response.");
  }
}
