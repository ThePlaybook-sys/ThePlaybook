import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AccountSummary } from "../AccountSummary";
import type { UserProfile } from "@/app/lib/api-types";

function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: "user-1",
    display_name: null,
    jurisdiction_state: "NJ",
    onboarding_completed_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("AccountSummary", () => {
  it("renders identity/jurisdiction and an honest no-active-subscription state", () => {
    render(
      <AccountSummary
        email="user@example.com"
        profile={makeProfile()}
        subscription={{ kind: "ok", data: { tier: null, status: null, billingPeriod: null, currentPeriodEnd: null } }}
      />,
    );
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("NJ")).toBeInTheDocument();
    expect(screen.getByText("No active subscription.")).toBeInTheDocument();
  });

  it("renders tier/status/billing period/renewal when a subscription is active", () => {
    render(
      <AccountSummary
        email="user@example.com"
        profile={makeProfile()}
        subscription={{
          kind: "ok",
          data: { tier: "elite", status: "active", billingPeriod: "monthly", currentPeriodEnd: "2026-10-01T00:00:00Z" },
        }}
      />,
    );
    expect(screen.getByText("elite")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("monthly")).toBeInTheDocument();
  });

  it("never fabricates a subscription when the read failed -- shows an honest unavailable message instead", () => {
    render(
      <AccountSummary email="user@example.com" profile={makeProfile()} subscription={{ kind: "error", status: 502 }} />,
    );
    expect(screen.getByText(/aren't available right now/)).toBeInTheDocument();
    expect(screen.queryByText("No active subscription.")).not.toBeInTheDocument();
  });

  it("links to How The Playbook Works", () => {
    render(
      <AccountSummary
        email="user@example.com"
        profile={makeProfile()}
        subscription={{ kind: "ok", data: { tier: null, status: null, billingPeriod: null, currentPeriodEnd: null } }}
      />,
    );
    const link = screen.getByRole("link", { name: "How The Playbook Works" });
    expect(link).toHaveAttribute("href", "/account/how-it-works");
  });

  it("renders a real sign-out form posting to /auth/sign-out", () => {
    const { container } = render(
      <AccountSummary
        email="user@example.com"
        profile={makeProfile()}
        subscription={{ kind: "ok", data: { tier: null, status: null, billingPeriod: null, currentPeriodEnd: null } }}
      />,
    );
    const form = container.querySelector("form[action='/auth/sign-out']");
    expect(form).not.toBeNull();
    expect(form).toHaveAttribute("method", "post");
  });
});
