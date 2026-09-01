import { describe, expect, it, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

const exchangeCodeForSession = vi.fn();

vi.mock("@/app/lib/supabase/server", () => ({
  createClient: () => ({ auth: { exchangeCodeForSession } }),
}));

describe("GET /auth/callback", () => {
  beforeEach(() => {
    exchangeCodeForSession.mockReset();
    exchangeCodeForSession.mockResolvedValue({ data: { session: { access_token: "jwt" } }, error: null });
  });

  it("real M6 defect #3 regression: redirects to the deployed public origin (from X-Forwarded-Host), never the internal request URL the Railway proxy connects on", async () => {
    const { GET } = await import("../route");
    const request = new NextRequest("http://localhost:8080/auth/callback?code=abc123", {
      headers: {
        "x-forwarded-host": "frontend-dev-ab32.up.railway.app",
        "x-forwarded-proto": "https",
      },
    });

    const response = await GET(request);

    expect(response.headers.get("location")).toBe("https://frontend-dev-ab32.up.railway.app/");
    expect(exchangeCodeForSession).toHaveBeenCalledWith("abc123");
  });

  it("falls back to the request's own origin with no forwarded headers -- local next dev", async () => {
    const { GET } = await import("../route");
    const request = new NextRequest("http://localhost:3000/auth/callback?code=abc123");

    const response = await GET(request);

    expect(response.headers.get("location")).toBe("http://localhost:3000/");
  });

  it("still redirects home (never throws/hangs) when no code is present", async () => {
    const { GET } = await import("../route");
    const request = new NextRequest("http://localhost:8080/auth/callback", {
      headers: { "x-forwarded-host": "frontend-dev-ab32.up.railway.app" },
    });

    const response = await GET(request);

    expect(response.headers.get("location")).toBe("https://frontend-dev-ab32.up.railway.app/");
    expect(exchangeCodeForSession).not.toHaveBeenCalled();
  });
});
