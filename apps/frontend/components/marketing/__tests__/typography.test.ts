import { describe, expect, it } from "vitest";
import { MARKETING_BODY_CLASS } from "../typography";

describe("MARKETING_BODY_CLASS (Public Web M2.1)", () => {
  it("applies the brightened body token with !important, so it reliably wins over Text's own text-text-secondary default", () => {
    expect(MARKETING_BODY_CLASS).toContain("!text-body-bright");
  });

  it("uses a medium weight, distinct from (lighter than) heading/display's bold weight", () => {
    expect(MARKETING_BODY_CLASS).toContain("font-medium");
    expect(MARKETING_BODY_CLASS).not.toMatch(/font-bold|font-semibold/);
  });
});
