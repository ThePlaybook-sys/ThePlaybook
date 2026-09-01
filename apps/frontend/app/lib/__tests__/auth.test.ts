import { describe, expect, it } from "vitest";
import { resolveRootDestination } from "../auth";

describe("resolveRootDestination", () => {
  it("routes a signed-out user to /sign-in", () => {
    expect(
      resolveRootDestination({ signedIn: false, hasProfile: false, onboardingCompletedAt: null }),
    ).toBe("/sign-in");
  });

  it("routes a signed-out user to /sign-in even if profile/onboarding data is somehow present -- signed-out always wins", () => {
    expect(
      resolveRootDestination({
        signedIn: false,
        hasProfile: true,
        onboardingCompletedAt: "2026-08-01T00:00:00Z",
      }),
    ).toBe("/sign-in");
  });

  it("routes a signed-in user with no profile row to /onboarding", () => {
    expect(
      resolveRootDestination({ signedIn: true, hasProfile: false, onboardingCompletedAt: null }),
    ).toBe("/onboarding");
  });

  it("routes a signed-in user with a profile but onboarding_completed_at null to /onboarding", () => {
    expect(
      resolveRootDestination({ signedIn: true, hasProfile: true, onboardingCompletedAt: null }),
    ).toBe("/onboarding");
  });

  it("routes a signed-in user with onboarding_completed_at set to /today", () => {
    expect(
      resolveRootDestination({
        signedIn: true,
        hasProfile: true,
        onboardingCompletedAt: "2026-08-01T00:00:00Z",
      }),
    ).toBe("/today");
  });
});
