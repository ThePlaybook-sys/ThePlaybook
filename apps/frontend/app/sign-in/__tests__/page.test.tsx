import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import SignInPage from "../page";

const getCurrentUserMock = vi.fn();
const redirectToRootDestinationMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
  redirectToRootDestination: () => redirectToRootDestinationMock(),
}));

vi.mock("@/app/lib/supabase/client", () => ({
  createClient: () => ({ auth: { signInWithPassword: vi.fn(), signUp: vi.fn() } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("SignInPage", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
    redirectToRootDestinationMock.mockReset();
  });

  it("defaults to the Sign In tab when no mode is given", async () => {
    render(await SignInPage({ searchParams: {} }));
    expect(screen.getByRole("tab", { name: "Sign In" })).toHaveAttribute("aria-selected", "true");
  });

  it("preselects the Create Account tab when linked from the landing page's CTA (?mode=sign-up)", async () => {
    render(await SignInPage({ searchParams: { mode: "sign-up" } }));
    expect(screen.getByRole("tab", { name: "Create Account" })).toHaveAttribute("aria-selected", "true");
  });

  it("treats any other mode value as sign-in, never erroring", async () => {
    render(await SignInPage({ searchParams: { mode: "something-else" } }));
    expect(screen.getByRole("tab", { name: "Sign In" })).toHaveAttribute("aria-selected", "true");
  });

  it("still bounces an already-signed-in user via the existing root-routing decision", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    await SignInPage({ searchParams: {} });
    expect(redirectToRootDestinationMock).toHaveBeenCalled();
  });
});
