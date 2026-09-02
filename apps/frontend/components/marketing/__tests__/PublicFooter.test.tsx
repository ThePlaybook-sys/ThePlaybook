import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PublicFooter } from "../PublicFooter";

describe("PublicFooter", () => {
  it("links to all four public destinations", () => {
    render(<PublicFooter />);
    expect(screen.getByRole("link", { name: "How It Works" })).toHaveAttribute("href", "/how-it-works");
    expect(screen.getByRole("link", { name: "Features" })).toHaveAttribute("href", "/features");
    expect(screen.getByRole("link", { name: "Pricing" })).toHaveAttribute("href", "/pricing");
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
  });

  it("shows a computed copyright year, never a hardcoded stale one", () => {
    render(<PublicFooter />);
    expect(screen.getByText(`© ${new Date().getFullYear()} MANSA. All rights reserved.`)).toBeInTheDocument();
  });

  it("never links to a Privacy or Terms page that doesn't exist yet", () => {
    render(<PublicFooter />);
    expect(screen.queryByRole("link", { name: /privacy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /terms/i })).not.toBeInTheDocument();
  });
});
