import { NextRequest, NextResponse } from "next/server";
import { DEMO_OPERATOR_COOKIE, gatewayUrl } from "../_gateway";

/**
 * Catch-all proxy for every other `/v1/demo/*` route on API Gateway
 * (scenarios, status, step, run, run-to-checkpoint, reset, games,
 * games/[id]/intelligence) -- one file instead of one per route, since
 * every one of them is an identical "forward method/body, forward
 * status/JSON back" shape (api-gateway/app/demo_routes.py's own `_proxy`
 * does the same thing one hop further in). No scenario/business logic
 * here either -- this is the third and last hop of one proxy chain, not
 * a new implementation of anything.
 */
async function proxy(request: NextRequest, path: string[]) {
  const token = request.cookies.get(DEMO_OPERATOR_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "not signed in to Demo Mode" }, { status: 401 });
  }

  const body = request.method === "GET" ? undefined : await request.text();
  let upstream: Response;
  try {
    upstream = await fetch(`${gatewayUrl()}/v1/demo/${path.join("/")}`, {
      method: request.method,
      headers: {
        "X-Demo-Operator-Token": token,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "could not reach API Gateway" }, { status: 502 });
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}
