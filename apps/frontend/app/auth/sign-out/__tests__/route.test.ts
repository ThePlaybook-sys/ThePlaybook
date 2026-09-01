import { describe, expect, it, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

const signOut = vi.fn();

vi.mock("@/app/lib/supabase/server", () => ({
  createClient: () => ({ auth: { signOut } }),
}));

describe("POST /auth/sign-out", () => {
  beforeEach(() => {
    signOut.mockReset();
    signOut.mockResolvedValue({ error: null });
  });

  it("real M6 defect #3 regression: redirects to the deployed public origin (from X-Forwarded-Host), never the internal request URL the Railway proxy connects on", async () => {
    const { POST } = await import("../route");
    const request = new NextRequest("http://localhost:8080/auth/sign-out", {
      method: "POST",
      headers: {
        "x-forwarded-host": "frontend-dev-ab32.up.railway.app",
        "x-forwarded-proto": "https",
      },
    });

    const response = await POST(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://frontend-dev-ab32.up.railway.app/sign-in");
  });

  it("falls back to the request's own origin with no forwarded headers -- local next dev", async () => {
    const { POST } = await import("../route");
    const request = new NextRequest("http://localhost:3000/auth/sign-out", { method: "POST" });

    const response = await POST(request);

    expect(response.headers.get("location")).toBe("http://localhost:3000/sign-in");
  });

  it("actually clears the session via auth.signOut() before redirecting -- the security requirement, not just the visible redirect", async () => {
    const { POST } = await import("../route");
    const request = new NextRequest("http://localhost:8080/auth/sign-out", {
      method: "POST",
      headers: { "x-forwarded-host": "frontend-dev-ab32.up.railway.app" },
    });

    await POST(request);

    expect(signOut).toHaveBeenCalledTimes(1);
  });
});
