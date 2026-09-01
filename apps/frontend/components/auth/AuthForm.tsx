"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Surface, Text } from "@/components/ds";
import { createClient } from "@/app/lib/supabase/client";

type Mode = "sign-in" | "sign-up";

/**
 * The one real sign-in/create-account form (Phase 6 Milestone 6),
 * replacing the manual `pb_session_token` workaround entirely. Calls
 * Supabase Auth directly from the browser (the anon key is the one
 * Supabase key safe to expose there) -- never a second, homegrown
 * authentication system, never a bypass.
 *
 * Deliberately does not assume DEV's email-confirmation setting either
 * way (verifying it directly was attempted and blocked by this
 * sandbox's own egress policy -- see the M6 close-out report): a
 * successful `signUp`/`signInWithPassword` call that returns a session
 * proceeds immediately; one that returns no session (confirmation
 * required) shows an honest "check your email" state instead of
 * erroring. Correct under either configuration, without guessing which
 * one DEV actually has.
 */
export function AuthForm() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setAwaitingConfirmation(false);

    // Every path below -- including one this codebase already hit in
    // real DEV validation (a misconfigured Supabase client throwing
    // synchronously, before any network call) -- must reach a visible
    // terminal state. A bare `await` with no try/catch left the button
    // stuck on "Please wait..." forever on any thrown exception, since
    // `setSubmitting(false)` was never reached. Never again: every code
    // path here ends in `finally { setSubmitting(false) }`.
    try {
      const supabase = createClient();
      const { data, error: authError } =
        mode === "sign-in"
          ? await supabase.auth.signInWithPassword({ email, password })
          : await supabase.auth.signUp({
              email,
              password,
              options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
            });

      if (authError) {
        setError(authError.message);
        return;
      }

      if (!data.session) {
        // Real, honest state under email-confirmation-required config --
        // never fabricated, never treated as an error.
        setAwaitingConfirmation(true);
        return;
      }

      router.refresh();
      router.push("/");
    } catch {
      // Any unexpected exception (a misconfigured client, a network
      // failure that throws rather than resolving with `error`, etc.)
      // -- surfaced honestly rather than left silent. Never the raw
      // exception message, which could leak internals the user can't
      // act on.
      setError("Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (awaitingConfirmation) {
    return (
      <Surface level="card" className="flex flex-col gap-sm p-lg">
        <Text variant="heading" as="h2">
          Check your email
        </Text>
        <Text variant="body">
          We sent a confirmation link to {email}. Follow it to finish creating your account.
        </Text>
      </Surface>
    );
  }

  return (
    <Surface level="card" className="flex flex-col gap-lg p-lg">
      <div className="flex gap-sm" role="tablist" aria-label="Sign in or create an account">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "sign-in"}
          onClick={() => setMode("sign-in")}
          className={`flex-1 rounded-sm py-sm text-label ${
            mode === "sign-in"
              ? "bg-surface-elevated text-text-primary"
              : "text-text-meta"
          }`}
        >
          Sign In
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "sign-up"}
          onClick={() => setMode("sign-up")}
          className={`flex-1 rounded-sm py-sm text-label ${
            mode === "sign-up"
              ? "bg-surface-elevated text-text-primary"
              : "text-text-meta"
          }`}
        >
          Create Account
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-md">
        <div className="flex flex-col gap-xs">
          <label htmlFor="email" className="text-label text-text-meta">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="min-h-[44px] rounded-sm border border-border-default bg-surface-page px-md py-sm text-base text-text-primary"
          />
        </div>

        <div className="flex flex-col gap-xs">
          <label htmlFor="password" className="text-label text-text-meta">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="min-h-[44px] rounded-sm border border-border-default bg-surface-page px-md py-sm text-base text-text-primary"
          />
        </div>

        {error && (
          <Text variant="body" className="text-state-negative">
            {error}
          </Text>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="min-h-[44px] rounded-sm bg-accent px-md py-sm text-base font-semibold text-surface-page disabled:opacity-60"
        >
          {submitting ? "Please wait..." : mode === "sign-in" ? "Sign In" : "Create Account"}
        </button>
      </form>
    </Surface>
  );
}
