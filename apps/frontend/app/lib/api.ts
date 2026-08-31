/**
 * Server-side fetch helpers for Phase 6 Milestone 3's read-only pages.
 * These run only in React Server Components (never in the browser --
 * `next/headers`'s `cookies()` is server-only by construction), calling
 * api-gateway directly over Railway's private network. No client-side
 * proxy route and no CORS configuration exist for these paths: unlike
 * `/demo`'s interactive tool, `/today`, `/recommendations`, and the
 * detail page never need the browser to call anything itself.
 *
 * `SESSION_COOKIE` is the one shared primitive this reads that M6 (auth
 * UI) doesn't exist to set yet -- HQ's M3 authorization allows shared
 * primitives genuinely necessary for M3. Nothing here issues, refreshes,
 * or validates a session; it only reads whatever raw Supabase access
 * token cookie is already present and forwards it as a Bearer token,
 * letting api-gateway's own `get_current_user` be the sole authority on
 * whether it's valid.
 */
import { cookies } from "next/headers";
import type {
  ApiResult,
  RecommendationCardData,
  RecommendationDetailData,
  RecommendationReconstruction,
} from "./api-types";

export const SESSION_COOKIE = "pb_session_token";

function gatewayUrl(): string {
  const url = process.env.API_GATEWAY_URL;
  if (!url) {
    throw new Error("API_GATEWAY_URL is not configured");
  }
  return url;
}

async function fetchFromGateway<T>(path: string): Promise<ApiResult<T>> {
  const token = cookies().get(SESSION_COOKIE)?.value;
  if (!token) {
    return { kind: "unauthenticated" };
  }

  let response: Response;
  try {
    response = await fetch(`${gatewayUrl()}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      // Every page reading this is per-user and time-sensitive
      // (freshness/withdrawal state) -- never let Next.js cache a
      // response meant for one viewer's session.
      cache: "no-store",
    });
  } catch {
    return { kind: "error", status: 502 };
  }

  if (response.status === 401) {
    return { kind: "unauthenticated" };
  }
  if (response.status === 404) {
    return { kind: "not_found" };
  }
  if (!response.ok) {
    return { kind: "error", status: response.status };
  }

  return { kind: "ok", data: (await response.json()) as T };
}

export function getToday(): Promise<ApiResult<RecommendationCardData[]>> {
  return fetchFromGateway<RecommendationCardData[]>("/v1/recommendations/today");
}

export function getRecommendations(params?: {
  since?: string;
  until?: string;
  limit?: number;
}): Promise<ApiResult<RecommendationCardData[]>> {
  const search = new URLSearchParams();
  if (params?.since) search.set("since", params.since);
  if (params?.until) search.set("until", params.until);
  if (params?.limit) search.set("limit", String(params.limit));
  const query = search.toString();
  return fetchFromGateway<RecommendationCardData[]>(
    `/v1/recommendations${query ? `?${query}` : ""}`,
  );
}

export function getRecommendationDetail(
  displayId: string,
): Promise<ApiResult<RecommendationDetailData>> {
  return fetchFromGateway<RecommendationDetailData>(
    `/v1/recommendations/${encodeURIComponent(displayId)}`,
  );
}

/** Milestone 4 (Time Machine) -- proxies ai-orchestrator's
 * `reconstruct_recommendation_product` (Milestone 5.3), reused
 * verbatim. This is the one and only historical-reconstruction read:
 * /history/[displayId] composes its six stages from this plus
 * `getRecommendationDetail` above, never deriving historical truth
 * itself. */
export function getRecommendationReconstruction(
  displayId: string,
): Promise<ApiResult<RecommendationReconstruction>> {
  return fetchFromGateway<RecommendationReconstruction>(
    `/v1/recommendations/${encodeURIComponent(displayId)}/reconstruction`,
  );
}
