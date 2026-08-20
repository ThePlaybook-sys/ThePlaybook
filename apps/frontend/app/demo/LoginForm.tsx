"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/**
 * Operator-token entry (Mac's Option A). Posts to this app's own
 * `/api/demo/login` route handler, which validates the token against
 * API Gateway before ever storing it in an httpOnly cookie -- this
 * component never sees or stores the token itself once submitted.
 */
export function LoginForm() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/demo/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!response.ok) {
        setError("Invalid demo operator token.");
        return;
      }
      router.refresh();
    } catch {
      setError("Could not reach the server.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 360, margin: "4rem auto", fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: "1.25rem", marginBottom: "0.5rem" }}>Demo Mode Operator Access</h1>
      <p style={{ color: "#525252", fontSize: "0.9rem", marginBottom: "1rem" }}>
        Enter the demo operator token to continue.
      </p>
      <form onSubmit={submit}>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Operator token"
          autoFocus
          style={{
            width: "100%",
            padding: "0.5rem",
            border: "1px solid #d4d4d4",
            borderRadius: 4,
            fontSize: "0.95rem",
            marginBottom: "0.75rem",
          }}
        />
        <button
          type="submit"
          disabled={submitting || !token}
          style={{
            width: "100%",
            padding: "0.6rem",
            background: "#1f2937",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            fontSize: "0.95rem",
            cursor: submitting || !token ? "not-allowed" : "pointer",
          }}
        >
          {submitting ? "Checking…" : "Enter"}
        </button>
        {error && <p style={{ color: "#b91c1c", fontSize: "0.85rem", marginTop: "0.5rem" }}>{error}</p>}
      </form>
    </div>
  );
}
