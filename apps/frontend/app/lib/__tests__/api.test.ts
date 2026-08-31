import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getCookie = vi.fn();

vi.mock("next/headers", () => ({
  cookies: () => ({ get: getCookie }),
}));

describe("api.ts fetch helpers", () => {
  const originalFetch = global.fetch;
  const originalEnv = process.env.API_GATEWAY_URL;

  beforeEach(() => {
    process.env.API_GATEWAY_URL = "http://api-gateway.internal:8080";
    getCookie.mockReset();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    process.env.API_GATEWAY_URL = originalEnv;
    vi.resetModules();
  });

  it("returns unauthenticated when no session cookie is present -- never treated as an error or empty state", async () => {
    getCookie.mockReturnValue(undefined);
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "unauthenticated" });
  });

  it("returns ok with the parsed body on a 200 response", async () => {
    getCookie.mockReturnValue({ value: "real-jwt" });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ displayId: "2026-00100" }]), { status: 200 }),
    ) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "ok", data: [{ displayId: "2026-00100" }] });
  });

  it("returns unauthenticated on a 401 -- an expired/invalid token is not a generic error", async () => {
    getCookie.mockReturnValue({ value: "expired-jwt" });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 401 })) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "unauthenticated" });
  });

  it("returns not_found on a 404 -- distinct from an empty ok result", async () => {
    getCookie.mockReturnValue({ value: "real-jwt" });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 404 })) as unknown as typeof fetch;
    const { getRecommendationDetail } = await import("../api");

    const result = await getRecommendationDetail("2026-00100");

    expect(result).toEqual({ kind: "not_found" });
  });

  it("returns error with the status on any other non-ok response", async () => {
    getCookie.mockReturnValue({ value: "real-jwt" });
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 502 })) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "error", status: 502 });
  });

  it("returns a 502 error when the upstream call throws (network failure)", async () => {
    getCookie.mockReturnValue({ value: "real-jwt" });
    global.fetch = vi.fn().mockRejectedValue(new Error("connection refused")) as unknown as typeof fetch;
    const { getToday } = await import("../api");

    const result = await getToday();

    expect(result).toEqual({ kind: "error", status: 502 });
  });
});
