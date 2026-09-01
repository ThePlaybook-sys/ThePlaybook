import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { resolveRequestOrigin } from "../request-origin";

describe("resolveRequestOrigin", () => {
  it("real M6 defect #3 regression: uses X-Forwarded-Host/X-Forwarded-Proto when present, never the internal request.url the Railway proxy connects on", () => {
    const request = new NextRequest("http://localhost:8080/auth/sign-out", {
      headers: {
        "x-forwarded-host": "frontend-dev-ab32.up.railway.app",
        "x-forwarded-proto": "https",
      },
    });

    expect(resolveRequestOrigin(request)).toBe("https://frontend-dev-ab32.up.railway.app");
  });

  it("defaults the forwarded protocol to https when X-Forwarded-Proto is absent but X-Forwarded-Host is present", () => {
    const request = new NextRequest("http://localhost:8080/auth/sign-out", {
      headers: { "x-forwarded-host": "frontend-dev-ab32.up.railway.app" },
    });

    expect(resolveRequestOrigin(request)).toBe("https://frontend-dev-ab32.up.railway.app");
  });

  it("falls back to the request's own origin when no forwarded headers are present -- local next dev, no proxy in front", () => {
    const request = new NextRequest("http://localhost:3000/auth/sign-out");

    expect(resolveRequestOrigin(request)).toBe("http://localhost:3000");
  });
});
