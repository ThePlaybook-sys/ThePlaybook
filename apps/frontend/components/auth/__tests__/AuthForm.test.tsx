import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthForm } from "../AuthForm";

const signInWithPassword = vi.fn();
const signUp = vi.fn();
const push = vi.fn();
const refresh = vi.fn();

vi.mock("@/app/lib/supabase/client", () => ({
  createClient: () => ({ auth: { signInWithPassword, signUp } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

async function fillAndSubmit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /sign in|create account/i }));
}

describe("AuthForm", () => {
  beforeEach(() => {
    signInWithPassword.mockReset();
    signUp.mockReset();
    push.mockReset();
    refresh.mockReset();
  });

  it("signs in successfully and hands off to root routing, never deciding the destination itself", async () => {
    signInWithPassword.mockResolvedValue({ data: { session: { access_token: "jwt" } }, error: null });
    render(<AuthForm />);

    await fillAndSubmit("user@example.com", "password123");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the real Supabase error message on failed sign-in, never a generic fallback", async () => {
    signInWithPassword.mockResolvedValue({
      data: { session: null },
      error: { message: "Invalid login credentials" },
    });
    render(<AuthForm />);

    await fillAndSubmit("user@example.com", "wrong-password");

    expect(await screen.findByText("Invalid login credentials")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows an honest 'check your email' state on sign-up when no session is returned -- never assumes email confirmation is on or off", async () => {
    signUp.mockResolvedValue({ data: { session: null }, error: null });
    render(<AuthForm />);

    fireEvent.click(screen.getByRole("tab", { name: "Create Account" }));
    await fillAndSubmit("new@example.com", "password123");

    expect(await screen.findByText("Check your email")).toBeInTheDocument();
    expect(screen.getByText(/new@example.com/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("proceeds immediately on sign-up when a session is returned -- also handled without assuming confirmation is required", async () => {
    signUp.mockResolvedValue({ data: { session: { access_token: "jwt" } }, error: null });
    render(<AuthForm />);

    fireEvent.click(screen.getByRole("tab", { name: "Create Account" }));
    await fillAndSubmit("new@example.com", "password123");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("mobile-safe structure: form inputs use 16px+ text and 44px+ tap targets", () => {
    render(<AuthForm />);

    const emailInput = screen.getByLabelText("Email");
    expect(emailInput).toHaveClass("text-base");
    expect(emailInput).toHaveClass("min-h-[44px]");

    const submitButton = screen.getByRole("button", { name: "Sign In" });
    expect(submitButton).toHaveClass("min-h-[44px]");
  });
});
