import { describe, expect, it, vi, beforeEach } from "vitest";

const getUser = vi.fn();
const redirectMock = vi.fn();

vi.mock("../supabase/server", () => ({
  createClient: () => ({ auth: { getUser } }),
}));

vi.mock("next/navigation", () => ({
  redirect: (destination: string) => {
    redirectMock(destination);
    throw new Error(`NEXT_REDIRECT:${destination}`);
  },
}));

describe("getCurrentUser / requireUser", () => {
  beforeEach(() => {
    getUser.mockReset();
    redirectMock.mockReset();
  });

  it("returns the user's id/email when a valid session exists", async () => {
    getUser.mockResolvedValue({ data: { user: { id: "user-1", email: "user@example.com" } } });
    const { getCurrentUser } = await import("../auth");

    const result = await getCurrentUser();

    expect(result).toEqual({ id: "user-1", email: "user@example.com" });
  });

  it("returns null for a signed-out request -- no user, no error thrown", async () => {
    getUser.mockResolvedValue({ data: { user: null } });
    const { getCurrentUser } = await import("../auth");

    const result = await getCurrentUser();

    expect(result).toBeNull();
  });

  it("returns null for a stale/invalid session -- getUser() itself round-trips to Supabase Auth to revalidate, so a tampered/expired token surfaces as no user, exactly like being signed out", async () => {
    getUser.mockResolvedValue({ data: { user: null }, error: { message: "invalid JWT" } });
    const { getCurrentUser } = await import("../auth");

    const result = await getCurrentUser();

    expect(result).toBeNull();
  });

  it("requireUser redirects to /sign-in when no user is present", async () => {
    getUser.mockResolvedValue({ data: { user: null } });
    const { requireUser } = await import("../auth");

    await expect(requireUser()).rejects.toThrow("NEXT_REDIRECT:/sign-in");
    expect(redirectMock).toHaveBeenCalledWith("/sign-in");
  });
});
