"use client";

import { LoginForm } from "./LoginForm";

/** Shown by any /demo page when its own data fetch 401s (a stale/wrong
 * cookie the layout's coarse check didn't catch) -- reuses the same
 * `LoginForm` rather than a second login implementation. */
export function AuthExpired() {
  return (
    <div>
      <p style={{ color: "#b91c1c", fontFamily: "system-ui, sans-serif", marginBottom: "1rem" }}>
        Your Demo Mode session has expired.
      </p>
      <LoginForm />
    </div>
  );
}
