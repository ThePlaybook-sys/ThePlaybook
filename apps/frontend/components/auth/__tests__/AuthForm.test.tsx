import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthForm } from "../AuthForm";

const signInWithPassword = vi.fn();
const signUp = vi.fn();
const push = vi.fn();
const refresh = vi.fn();
const createClientMock = vi.fn(() => ({ auth: { signInWithPassword, signUp } }));

vi.mock("@/app/lib/supabase/client", () => ({
  createClient: () => createClientMock(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

async function fillAndSubmit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /sign in|create account|please wait/i }));
}

describe("AuthForm", () => {
  beforeEach(() => {
    signInWithPassword.mockReset();
    signUp.mockReset();
    push.mockReset();
    refresh.mockReset();
    createClientMock.mockReset();
    createClientMock.mockImplementation(() => ({ auth: { signInWithPassword, signUp } }));
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

  it("shows 'Please wait...' and disables the button while the request is pending", async () => {
    let resolveSignIn: (value: unknown) => void = () => {};
    signInWithPassword.mockReturnValue(
      new Promise((resolve) => {
        resolveSignIn = resolve;
      }),
    );
    render(<AuthForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    const pendingButton = await screen.findByRole("button", { name: "Please wait..." });
    expect(pendingButton).toBeDisabled();

    resolveSignIn({ data: { session: { access_token: "jwt" } }, error: null });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("real M6 defect regression: a client that throws synchronously (e.g. a misconfigured/missing Supabase URL) never leaves the button stuck on 'Please wait...' -- it shows an error and re-enables the form", async () => {
    createClientMock.mockImplementation(() => {
      throw new Error("supabaseUrl is required.");
    });
    render(<AuthForm />);

    await fillAndSubmit("user@example.com", "password123");

    expect(await screen.findByText("Something went wrong. Try again.")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Sign In" });
    expect(button).not.toBeDisabled();
    expect(push).not.toHaveBeenCalled();
  });

  it("a rejected auth call (e.g. a network failure that throws rather than resolving with an error field) also surfaces an error and resets the pending state", async () => {
    signInWithPassword.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<AuthForm />);

    await fillAndSubmit("user@example.com", "password123");

    expect(await screen.findByText("Something went wrong. Try again.")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Sign In" });
    expect(button).not.toBeDisabled();
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
