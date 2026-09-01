import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * M7.3 §2/§6/§10/§14 -- static-source proofs that cannot be verified by
 * rendering alone: this route's source files themselves must never gain
 * a code path capable of a backend mutation, a fabricated modeled-
 * probability number, or a fabricated logo/abbreviation, regardless of
 * what today's fixtures happen to contain. Mirrors the same static-scan
 * method `components/dashboard/__tests__/no-modeled-probability.test.ts`
 * already established in M7.1.
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

const previewDir = join(__dirname, "..");
const sourceFiles = readAllSourceFiles(previewDir);
const combinedSource = sourceFiles.map((file) => readFileSync(file, "utf-8")).join("\n");

describe("MANSA UI Preview never gains a backend mutation path", () => {
  it("no source file imports app/lib/api.ts's fetch helpers", () => {
    expect(combinedSource).not.toMatch(/from ["']@\/app\/lib\/api["']/);
  });

  it("no source file calls fetch(...) directly", () => {
    expect(combinedSource).not.toMatch(/\bfetch\s*\(/);
  });

  it("no source file constructs or imports a Supabase client", () => {
    // Matches actual code usage (an import specifier or a client
    // constructor call) -- not the word "Supabase" in prose, which this
    // module's own doc comments use to explicitly disclaim any such
    // dependency.
    expect(combinedSource).not.toMatch(/from ["']@supabase\//);
    expect(combinedSource).not.toMatch(/createServerClient\s*\(|createBrowserClient\s*\(/);
  });
});

describe("MANSA UI Preview never fabricates a modeled-probability number", () => {
  it("no preview source file mentions 'probability' anywhere", () => {
    const offenders = sourceFiles.filter((file) => /probability/i.test(readFileSync(file, "utf-8")));
    expect(offenders).toEqual([]);
  });
});

describe("MANSA UI Preview never fabricates team logos or abbreviations", () => {
  it("no preview source file renders an <img> or next/image logo asset", () => {
    expect(combinedSource).not.toMatch(/<img\b/i);
    expect(combinedSource).not.toMatch(/from ["']next\/image["']/);
  });

  it("every fixture team name is a real full team name, never a short invented abbreviation", () => {
    const fixturesSource = readFileSync(join(previewDir, "fixtures.ts"), "utf-8");
    const teamNameMatches = [...fixturesSource.matchAll(/(?:homeTeam|awayTeam):\s*"([^"]+)"/g)].map(
      (match) => match[1],
    );
    expect(teamNameMatches.length).toBeGreaterThan(0);
    for (const name of teamNameMatches) {
      // A real full NFL team name is always multi-word; a short all-caps
      // token (e.g. "SF", "JAX", "KC") would be an invented abbreviation.
      expect(name).not.toMatch(/^[A-Z]{2,4}$/);
      expect(name.split(" ").length).toBeGreaterThan(1);
    }
  });
});
