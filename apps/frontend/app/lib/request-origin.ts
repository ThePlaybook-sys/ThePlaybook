import type { NextRequest } from "next/server";

/**
 * Real M6 defect #3: `next start` binds to the container's internal
 * port (the Railway-injected `PORT`, e.g. 8080) and a Route Handler's
 * `request.url` reflects that internal loopback connection, not the
 * public deployed origin -- observed live as Sign Out redirecting to
 * `http://localhost:8080` / ERR_CONNECTION_REFUSED. Railway's edge
 * always sets `X-Forwarded-Proto` (always `https`) and `X-Forwarded-Host`
 * (the original public host) on every request (Railway's own docs), so
 * those are the source of truth for building an absolute redirect target
 * in a Route Handler. Falls back to the request's own origin when the
 * headers are absent -- local `next dev` has no proxy in front of it.
 */
export function resolveRequestOrigin(request: NextRequest): string {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
  if (forwardedHost) {
    return `${forwardedProto}://${forwardedHost}`;
  }
  return new URL(request.url).origin;
}
