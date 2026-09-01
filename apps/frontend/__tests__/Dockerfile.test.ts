import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Regression guard for the real M6 DEV defect: Railway's Dockerfile
 * builds are isolated from service variables unless explicitly declared
 * with `ARG` (confirmed via Railway's own docs). Missing this caused
 * `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` to be
 * `undefined` in the built client bundle, and `createBrowserClient`
 * to throw synchronously on first use -- observed live as "Create
 * Account" hanging forever on "Please wait...".
 */
describe("Dockerfile", () => {
  const dockerfile = readFileSync(join(__dirname, "..", "Dockerfile"), "utf-8");

  it("declares NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY as build ARGs before npm run build", () => {
    const buildLineIndex = dockerfile.indexOf("RUN npm run build");
    expect(buildLineIndex).toBeGreaterThan(-1);

    const beforeBuild = dockerfile.slice(0, buildLineIndex);
    expect(beforeBuild).toMatch(/ARG NEXT_PUBLIC_SUPABASE_URL/);
    expect(beforeBuild).toMatch(/ARG NEXT_PUBLIC_SUPABASE_ANON_KEY/);
    expect(beforeBuild).toMatch(/ENV NEXT_PUBLIC_SUPABASE_URL=\$NEXT_PUBLIC_SUPABASE_URL/);
    expect(beforeBuild).toMatch(/ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=\$NEXT_PUBLIC_SUPABASE_ANON_KEY/);
  });
});
