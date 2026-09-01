import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Container, StateBadge, Surface, Text } from "..";

describe("Surface", () => {
  it("renders each spatial level with its own data attribute", () => {
    const { rerender } = render(<Surface level="page" data-testid="surface" />);
    expect(screen.getByTestId("surface")).toHaveAttribute("data-surface-level", "page");

    rerender(<Surface level="card" data-testid="surface" />);
    expect(screen.getByTestId("surface")).toHaveAttribute("data-surface-level", "card");

    rerender(<Surface level="elevated" data-testid="surface" />);
    expect(screen.getByTestId("surface")).toHaveAttribute("data-surface-level", "elevated");
  });
});

describe("Text", () => {
  it("renders each typography role with the correct default tag", () => {
    render(<Text variant="display">Verdict</Text>);
    expect(screen.getByText("Verdict").tagName).toBe("H1");

    render(<Text variant="data">89%</Text>);
    const dataEl = screen.getByText("89%");
    expect(dataEl.tagName).toBe("SPAN");
    expect(dataEl).toHaveAttribute("data-text-variant", "data");
  });

  it("allows overriding the rendered tag without losing the variant", () => {
    render(
      <Text variant="body" as="strong">
        Emphasis
      </Text>,
    );
    expect(screen.getByText("Emphasis").tagName).toBe("STRONG");
  });
});

describe("StateBadge", () => {
  it("renders the label and exposes its tone for styling/testing", () => {
    render(<StateBadge tone="positive" label="WIN" />);
    const badge = screen.getByText("WIN");
    expect(badge).toHaveAttribute("data-state-tone", "positive");
  });

  it.each(["positive", "negative", "neutral"] as const)(
    "supports the %s tone",
    (tone) => {
      render(<StateBadge tone={tone} label={tone} />);
      expect(screen.getByText(tone)).toHaveAttribute("data-state-tone", tone);
    },
  );
});

describe("Container", () => {
  it("renders its children", () => {
    render(
      <Container>
        <span>Inside</span>
      </Container>,
    );
    expect(screen.getByText("Inside")).toBeInTheDocument();
  });

  it("defaults to a div but can render as a real <main> landmark (M7 accessibility pass)", () => {
    const { container, rerender } = render(<Container data-testid="c">Inside</Container>);
    expect(container.querySelector("div[data-testid='c']")).not.toBeNull();

    rerender(
      <Container as="main" data-testid="c">
        Inside
      </Container>,
    );
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});
