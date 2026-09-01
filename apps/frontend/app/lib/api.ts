/**
 * Server-side fetch helpers for every Phase 6 authenticated page. These
 * run only in React Server Components/Server Actions/Route Handlers
 * (never in the browser), calling api-gateway directly over Railway's
 * private network. No client-side proxy route and no CORS
 * configuration exist for these paths: unlike `/demo`'s interactive
 * tool, these pages never need the browser to call anything itself.
 *
 * Milestone 6 replaces M3's placeholder raw `pb_session_token` cookie
 * read (which never issued, refreshed, or validated anything itself --
 * see that module's own prior docstring) with the real Supabase SSR
 * session `middleware.ts` now keeps fresh. This is not an architecture
 * conflict: M3's own comment already named this exact gap as M6's job
 * to close. api-gateway's contract is unchanged either way -- it only
 * ever wanted `Authorization: Bearer <supabase access token>`, and lets
 * its own `get_current_user` be the sole authority on whether that
 * token is valid.
 */
import type {
  ApiResult,
  OnboardingUpdate,
  RecommendationCardData,
  RecommendationDetailData,
  RecommendationReconstruction,
  SubscriptionData,
  TrackRecordData,
  UserProfile,
} from "./api-types";
import { createClient } from "./supabase/server";

function gatewayUrl(): string {
  const url = process.env.API_GATEWAY_URL;
  if (!url) {
    throw new Error("API_GATEWAY_URL is not configured");
  }
  return url;
}

async function getAccessToken(): Promise<string | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

async function callGateway<T>(
  path: string,
  init?: { method?: "GET" | "PATCH"; body?: unknown },
): Promise<ApiResult<T>> {
  const token = await getAccessToken();
  if (!token) {
    return { kind: "unauthenticated" };
  }

  let response: Response;
  try {
    response = await fetch(`${gatewayUrl()}${path}`, {
      method: init?.method ?? "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
      body: init?.body ? JSON.stringify(init.body) : undefined,
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
  return callGateway<RecommendationCardData[]>("/v1/recommendations/today");
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
  return callGateway<RecommendationCardData[]>(
    `/v1/recommendations${query ? `?${query}` : ""}`,
  );
}

export function getRecommendationDetail(
  displayId: string,
): Promise<ApiResult<RecommendationDetailData>> {
  return callGateway<RecommendationDetailData>(
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
  return callGateway<RecommendationReconstruction>(
    `/v1/recommendations/${encodeURIComponent(displayId)}/reconstruction`,
  );
}

/** Milestone 5 (Track Record) -- reuses the existing M2 `/v1/track-record`
 * read model verbatim. No new grading algorithm, no derived win-rate:
 * `/track-record` renders exactly the counts and sample status this
 * route already returns. */
export function getTrackRecord(): Promise<ApiResult<TrackRecordData>> {
  return callGateway<TrackRecordData>("/v1/track-record");
}

/** Milestone 6 -- reuses the existing Phase 2 `GET /v1/user/profile`
 * route verbatim. `not_found` genuinely means "no user_profiles row
 * yet" (should not happen post-signup given the DB trigger, but the
 * route itself can 404, so it's handled honestly rather than assumed
 * impossible). */
export function getUserProfile(): Promise<ApiResult<UserProfile>> {
  return callGateway<UserProfile>("/v1/user/profile");
}

/** Milestone 6 -- reuses the existing Phase 2 `PATCH /v1/user/profile`
 * route verbatim. Only `jurisdiction_state` is ever sent from M6's
 * onboarding form (HQ's explicit "keep onboarding short" instruction);
 * every other optional field on that route's own schema is left unset. */
export function updateOnboarding(update: OnboardingUpdate): Promise<ApiResult<UserProfile>> {
  return callGateway<UserProfile>("/v1/user/profile", { method: "PATCH", body: update });
}

/** Milestone 6 -- reuses the existing M2 `GET /v1/user/subscription`
 * route verbatim. Displays only the authenticated user's own tier/
 * status; no entitlement reinterpretation happens here. */
export function getSubscription(): Promise<ApiResult<SubscriptionData>> {
  return callGateway<SubscriptionData>("/v1/user/subscription");
}
