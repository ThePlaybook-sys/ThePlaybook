import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// vitest.config.ts doesn't enable `test.globals`, so React Testing
// Library's own automatic per-test cleanup (which detects a global
// `afterEach`) never registers -- without this, DOM from one test
// leaks into the next within the same file, causing spurious
// "multiple elements found" failures whenever two tests render
// overlapping text (e.g. the same team name across fixtures).
afterEach(() => {
  cleanup();
});
