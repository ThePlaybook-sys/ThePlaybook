/**
 * Shared helper for every /api/demo/* route handler (DEMO-4).
 *
 * These route handlers run server-side in the Next.js server, never in
 * the browser -- Decision 1's "do NOT allow Frontend -> sports-intel-layer
 * directly" (and, implicitly, no direct Supabase access either) is
 * satisfied by construction here: the only outbound call this file makes
 * is to API_GATEWAY_URL, nothing else. The browser only ever talks to
 * this Next.js app's own origin (`/api/demo/...`), so there is no CORS
 * configuration to add anywhere, and the demo-operator token lives in an
 * httpOnly cookie the browser's own JavaScript never reads.
 */
export const DEMO_OPERATOR_COOKIE = "demo_operator_token";

export function gatewayUrl(): string {
  const url = process.env.API_GATEWAY_URL;
  if (!url) {
    throw new Error("API_GATEWAY_URL is not configured");
  }
  return url;
}
