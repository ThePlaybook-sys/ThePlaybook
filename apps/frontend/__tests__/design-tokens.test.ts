import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Real M7 findings: several className strings referenced custom Tailwind
 * color tokens that were never actually generated, so Tailwind silently
 * dropped the rule instead of erroring -- `border-border-default` (no
 * `border.default` key existed, only `border.DEFAULT`), `bg-border-default`
 * (same), `outline-accent-primary`/`border-accent-primary` (the token is
 * named `accent`, not `accent-primary`), and `bg-state-positive/15`/
 * `border-state-positive/30` (opacity modifiers on a bare `var(--x)` hex
 * color silently drop instead of applying -- Tailwind needs the RGB-triplet
 * `rgb(var(--x) / <alpha-value>)` pattern to support them). The last one
 * meant every StateBadge (Win/Loss/Push/Void/Mixed Settled/Withdrawn)
 * rendered with no background tint or border color at all -- text only.
 * These guards catch the exact broken literals recurring, and the
 * config/token shape that made the opacity modifiers work.
 */

function readAllTsx(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "__tests__" || entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      readAllTsx(full, out);
    } else if (entry.endsWith(".tsx")) {
      out.push(full);
    }
  }
  return out;
}

const root = join(__dirname, "..");
const sourceFiles = [...readAllTsx(join(root, "app")), ...readAllTsx(join(root, "components"))];
const allSource = sourceFiles.map((f) => readFileSync(f, "utf-8")).join("\n");

describe("design token class names", () => {
  it("never reintroduces border-border-default / bg-border-default -- only border.DEFAULT exists, generating border-border / bg-border", () => {
    expect(allSource).not.toMatch(/\bborder-border-default\b/);
    expect(allSource).not.toMatch(/\bbg-border-default\b/);
  });

  it("never reintroduces the accent-primary token name -- the generated Tailwind color is `accent`, not `accent-primary`", () => {
    expect(allSource).not.toMatch(/-accent-primary\b/);
  });

  it("tailwind.config.ts wraps state colors in rgb(var(...) / <alpha-value>), not a bare var() -- required for bg-state-*/NN and border-state-*/NN opacity modifiers to actually apply", () => {
    const config = readFileSync(join(root, "tailwind.config.ts"), "utf-8");
    expect(config).toMatch(/positive:\s*"rgb\(var\(--state-positive\)\s*\/\s*<alpha-value>\)"/);
    expect(config).toMatch(/negative:\s*"rgb\(var\(--state-negative\)\s*\/\s*<alpha-value>\)"/);
    expect(config).toMatch(/neutral:\s*"rgb\(var\(--state-neutral\)\s*\/\s*<alpha-value>\)"/);
  });

  it("globals.css defines --state-* as space-separated RGB channels, not a hex string -- rgb(var(...)) requires the unwrapped channel format", () => {
    const css = readFileSync(join(root, "app/globals.css"), "utf-8");
    expect(css).toMatch(/--state-positive:\s*\d+\s+\d+\s+\d+;/);
    expect(css).toMatch(/--state-negative:\s*\d+\s+\d+\s+\d+;/);
    expect(css).toMatch(/--state-neutral:\s*\d+\s+\d+\s+\d+;/);
    expect(css).not.toMatch(/--state-positive:\s*#/);
  });
});
