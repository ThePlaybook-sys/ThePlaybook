import { NextRequest, NextResponse } from "next/server";
import { DEMO_OPERATOR_COOKIE, gatewayUrl } from "../_gateway";

/**
 * Validates an operator-entered token against API Gateway's own
 * `/v1/demo/login` (which validates it against `DEMO_OPERATOR_TOKEN`)
 * before ever storing it -- never accepts a token client-side without
 * this round trip succeeding first.
 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const token = typeof body?.token === "string" ? body.token : "";
  if (!token) {
    return NextResponse.json({ ok: false, error: "token is required" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${gatewayUrl()}/v1/demo/login`, {
      method: "POST",
      headers: { "X-Demo-Operator-Token": token },
    });
  } catch {
    return NextResponse.json({ ok: false, error: "could not reach API Gateway" }, { status: 502 });
  }

  if (!upstream.ok) {
    return NextResponse.json({ ok: false }, { status: upstream.status });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(DEMO_OPERATOR_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
  return response;
}
