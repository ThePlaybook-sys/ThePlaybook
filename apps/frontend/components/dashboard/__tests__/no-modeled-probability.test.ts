import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Real M7.1 product/data-contract gap, recorded explicitly rather than
 * solved silently (HQ's instruction): no `/v1/recommendations*` route
 * exposes a modeled-probability field -- only `finalAggregateConfidence`
 * (confidence) and `evPerDollar` (EV) exist. This guard scans every
 * Command Center source file for the word "probability" so a future
 * change can never quietly introduce a fabricated or derived modeled-
 * probability number into the dashboard without this test failing.
 */
function readAllSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "__tests__" || entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      readAllSourceFiles(full, out);
    } else if (entry.endsWith(".ts") || entry.endsWith(".tsx")) {
      out.push(full);
    }
  }
  return out;
}

describe("Command Center never fabricates a modeled-probability number", () => {
  it("no dashboard component or the /today page mentions 'probability' anywhere", () => {
    const dashboardDir = join(__dirname, "..");
    const todayPageDir = join(__dirname, "..", "..", "..", "app", "today");
    const files = [...readAllSourceFiles(dashboardDir), ...readAllSourceFiles(todayPageDir)];

    const offenders = files.filter((file) => /probability/i.test(readFileSync(file, "utf-8")));

    expect(offenders).toEqual([]);
  });
});
