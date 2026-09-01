"use client";

import { useState, type FormEvent } from "react";
import { Text } from "@/components/ds";
import { US_STATES } from "@/app/lib/us-states";
import { completeOnboarding } from "@/app/onboarding/actions";

/** The only onboarding field this milestone collects -- `jurisdiction_state`,
 * required by the existing `PATCH /v1/user/profile` contract (Phase 2
 * Milestone 4). Framed here as availability varying by state, not a
 * legal claim -- Volume 1 §10 is explicit that jurisdiction gating is a
 * business-planning input, not a legal opinion this codebase makes. */
export function OnboardingForm() {
  const [jurisdictionState, setJurisdictionState] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const result = await completeOnboarding(jurisdictionState);
    // A successful save redirects server-side before this line ever runs
    // (redirect() throws its own control-flow signal) -- reaching here
    // always means ok: false.
    setSubmitting(false);
    if (!result.ok) {
      setError(result.error);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-md">
      <div className="flex flex-col gap-xs">
        <label htmlFor="jurisdiction_state" className="text-label text-text-meta">
          Your State
        </label>
        <select
          id="jurisdiction_state"
          name="jurisdiction_state"
          required
          value={jurisdictionState}
          onChange={(event) => setJurisdictionState(event.target.value)}
          className="min-h-[44px] rounded-sm border border-border bg-surface-page px-md py-sm text-base text-text-primary"
        >
          <option value="" disabled>
            Select your state
          </option>
          {US_STATES.map((state) => (
            <option key={state.code} value={state.code}>
              {state.name}
            </option>
          ))}
        </select>
        <Text variant="label" as="span">
          Availability can vary by state, so we ask before you get started.
        </Text>
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
        {submitting ? "Saving..." : "Continue"}
      </button>
    </form>
  );
}
