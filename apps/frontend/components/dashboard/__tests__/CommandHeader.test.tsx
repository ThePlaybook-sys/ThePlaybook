import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CommandHeader } from "../CommandHeader";

describe("CommandHeader", () => {
  it("renders MANSA / Sports Intelligence as the entry band's identity, as an h1", () => {
    render(<CommandHeader freshness={{ kind: "unauthenticated" }} />);
    expect(screen.getByRole("heading", { level: 1, name: "MANSA" })).toBeInTheDocument();
    expect(screen.getByText("Sports Intelligence")).toBeInTheDocument();
  });

  it("never renders the mantra -- that brand moment is reserved for /sign-in only, per HQ's 'do not plaster it' instruction", () => {
    render(<CommandHeader freshness={{ kind: "unauthenticated" }} />);
    expect(screen.queryByText(/See the game/)).not.toBeInTheDocument();
  });

  it("renders the source-freshness state when the read succeeds", () => {
    render(
      <CommandHeader
        freshness={{ kind: "ok", data: { status: null, startedAt: null, completedAt: null, gamesInSlate: null } }}
      />,
    );
    expect(screen.getByText("Awaiting first data refresh")).toBeInTheDocument();
  });
});
