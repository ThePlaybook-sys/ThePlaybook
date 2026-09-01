import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getSession = vi.fn();

vi.mock("../supabase/server", () => ({
  createClient: () => ({ auth: { getSession } }),
}));

describe("api.ts fetch helpers", () => {
  const originalFetch = global.fetch;
  const originalEnv = process.env.API_GATEWAY_URL;

  beforeEach(() => {
    process.env.API_GATEWAY_URL = "http://api-gateway.internal:8080";
    getSession.mockReset();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    process.env.API_GATEWAY_URL = originalEnv;
    vi.resetModules();
  });

  it("returns unauthenticated when no session is present -- never treated as an error or empty state", async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "unauthenticated" });
  });

  it("returns ok with the parsed body on a 200 response", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ displayId: "2026-00100" }]), { status: 200 }),
    ) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "ok", data: [{ displayId: "2026-00100" }] });
  });

  it("returns unauthenticated on a 401 -- an expired/invalid token is not a generic error", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "expired-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 401 })) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "unauthenticated" });
  });

  it("returns not_found on a 404 -- distinct from an empty ok result", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 404 })) as unknown as typeof fetch;
    const { getRecommendationDetail } = await import("../api");

    const result = await getRecommendationDetail("2026-00100");

    expect(result).toEqual({ kind: "not_found" });
  });

  it("returns error with the status on any other non-ok response", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 502 })) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "error", status: 502 });
  });

  it("returns a 502 error when the upstream call throws (network failure)", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockRejectedValue(new Error("connection refused")) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "error", status: 502 });
  });

  it("Milestone 4: getRecommendationReconstruction returns ok with the raw reconstruction shape on 200", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ strategy_version: "v1", legs: [] }), { status: 200 }),
    ) as unknown as typeof fetch;
    const { getRecommendationReconstruction } = await import("../api");

    const result = await getRecommendationReconstruction("2026-00100");

    expect(result).toEqual({ kind: "ok", data: { strategy_version: "v1", legs: [] } });
  });

  it("Milestone 4: getRecommendationReconstruction returns not_found when the activation snapshot doesn't exist -- never fabricated", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 404 })) as unknown as typeof fetch;
    const { getRecommendationReconstruction } = await import("../api");

    const result = await getRecommendationReconstruction("2026-00100");

    expect(result).toEqual({ kind: "not_found" });
  });

  it("Milestone 4: getRecommendationReconstruction returns error when ai-orchestrator is unreachable via the api-gateway proxy", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 502 })) as unknown as typeof fetch;
    const { getRecommendationReconstruction } = await import("../api");

    const result = await getRecommendationReconstruction("2026-00100");

    expect(result).toEqual({ kind: "error", status: 502 });
  });

  it("Milestone 6: getUserProfile returns ok with the raw user_profiles row on 200", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ id: "user-1", jurisdiction_state: "NJ", onboarding_completed_at: null }),
        { status: 200 },
      ),
    ) as unknown as typeof fetch;
    const { getUserProfile } = await import("../api");

    const result = await getUserProfile();

    expect(result).toEqual({
      kind: "ok",
      data: { id: "user-1", jurisdiction_state: "NJ", onboarding_completed_at: null },
    });
  });

  it("Milestone 6: updateOnboarding PATCHes only jurisdiction_state and returns the updated profile", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "user-1", jurisdiction_state: "NJ" }), { status: 200 }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    const { updateOnboarding } = await import("../api");

    const result = await updateOnboarding({ jurisdiction_state: "NJ" });

    expect(result).toEqual({ kind: "ok", data: { id: "user-1", jurisdiction_state: "NJ" } });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ jurisdiction_state: "NJ" });
  });

  it("Milestone 6: getSubscription returns ok with the camelCase subscription shape on 200", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ tier: "elite", status: "active", billingPeriod: "monthly", currentPeriodEnd: "2026-10-01T00:00:00Z" }),
        { status: 200 },
      ),
    ) as unknown as typeof fetch;
    const { getSubscription } = await import("../api");

    const result = await getSubscription();

    expect(result).toEqual({
      kind: "ok",
      data: { tier: "elite", status: "active", billingPeriod: "monthly", currentPeriodEnd: "2026-10-01T00:00:00Z" },
    });
  });

  it("Milestone 7.1: getSourceFreshness returns ok with the raw freshness shape on 200", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "real-jwt" } } });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ status: "success", startedAt: "2026-09-02T06:00:00Z", completedAt: "2026-09-02T06:04:12Z", gamesInSlate: 14 }),
        { status: 200 },
      ),
    ) as unknown as typeof fetch;
    const { getSourceFreshness } = await import("../api");

    const result = await getSourceFreshness();

    expect(result).toEqual({
      kind: "ok",
      data: { status: "success", startedAt: "2026-09-02T06:00:00Z", completedAt: "2026-09-02T06:04:12Z", gamesInSlate: 14 },
    });
  });
});
