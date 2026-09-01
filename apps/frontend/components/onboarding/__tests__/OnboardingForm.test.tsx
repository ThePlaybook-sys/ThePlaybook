import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { OnboardingForm } from "../OnboardingForm";

const completeOnboarding = vi.fn();

vi.mock("@/app/onboarding/actions", () => ({
  completeOnboarding: (jurisdictionState: string) => completeOnboarding(jurisdictionState),
}));

describe("OnboardingForm", () => {
  beforeEach(() => {
    completeOnboarding.mockReset();
  });

  it("submits the selected jurisdiction_state to the action", async () => {
    completeOnboarding.mockResolvedValue({ ok: true });
    render(<OnboardingForm />);

    fireEvent.change(screen.getByLabelText("Your State"), { target: { value: "NJ" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(completeOnboarding).toHaveBeenCalledWith("NJ"));
  });

  it("shows the action's real error message on save failure, never a generic one", async () => {
    completeOnboarding.mockResolvedValue({ ok: false, error: "Something went wrong saving that. Try again." });
    render(<OnboardingForm />);

    fireEvent.change(screen.getByLabelText("Your State"), { target: { value: "NJ" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Something went wrong saving that. Try again.")).toBeInTheDocument();
  });

  it("requires a state to be selected before it can be submitted natively", () => {
    render(<OnboardingForm />);
    const select = screen.getByLabelText("Your State") as HTMLSelectElement;
    expect(select).toBeRequired();
    expect(select.value).toBe("");
  });

  it("mobile-safe structure: the select and submit button use 16px+ text and 44px+ tap targets", () => {
    render(<OnboardingForm />);

    const select = screen.getByLabelText("Your State");
    expect(select).toHaveClass("text-base");
    expect(select).toHaveClass("min-h-[44px]");

    const submitButton = screen.getByRole("button", { name: "Continue" });
    expect(submitButton).toHaveClass("min-h-[44px]");
  });
});
