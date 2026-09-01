import { describe, expect, it } from "vitest";
import { formatRelativeTime } from "../format";

const NOW = new Date("2026-09-02T06:10:00Z");

describe("formatRelativeTime", () => {
  it("returns an empty string for a null timestamp", () => {
    expect(formatRelativeTime(null, NOW)).toBe("");
  });

  it("returns 'just now' for a timestamp under a minute old", () => {
    expect(formatRelativeTime("2026-09-02T06:09:45Z", NOW)).toBe("just now");
  });

  it("returns minutes for a timestamp under an hour old", () => {
    expect(formatRelativeTime("2026-09-02T06:06:00Z", NOW)).toBe("4 min ago");
  });

  it("returns hours for a timestamp under a day old", () => {
    expect(formatRelativeTime("2026-09-02T03:10:00Z", NOW)).toBe("3 hr ago");
  });

  it("returns days for a timestamp under a week old, singular for exactly one day", () => {
    expect(formatRelativeTime("2026-08-31T06:10:00Z", NOW)).toBe("2 days ago");
    expect(formatRelativeTime("2026-09-01T06:10:00Z", NOW)).toBe("1 day ago");
  });

  it("falls back to an absolute date past a week old rather than an increasingly meaningless day count", () => {
    expect(formatRelativeTime("2026-08-01T06:10:00Z", NOW)).toBe("Aug 1, 6:10 AM");
  });

  it("falls back to an absolute date for a timestamp in the future (clock skew), never a negative duration", () => {
    expect(formatRelativeTime("2026-09-02T07:00:00Z", NOW)).toBe("Sep 2, 7:00 AM");
  });
});
