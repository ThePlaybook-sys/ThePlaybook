import { NextResponse } from "next/server";
import { DEMO_OPERATOR_COOKIE } from "../_gateway";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(DEMO_OPERATOR_COOKIE);
  return response;
}
