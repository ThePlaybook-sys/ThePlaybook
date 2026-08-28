import type { HTMLAttributes } from "react";

type SurfaceLevel = "page" | "card" | "elevated";

const LEVEL_CLASS: Record<SurfaceLevel, string> = {
  page: "bg-surface-page",
  card: "bg-surface-card border border-border rounded-md",
  elevated: "bg-surface-elevated border border-border rounded-lg",
};

export type SurfaceProps = HTMLAttributes<HTMLDivElement> & {
  level: SurfaceLevel;
};

/**
 * The three spatial levels the four-layer progressive-disclosure model
 * and Time Machine's staged narrative rely on (Volume 5 v5.0 §4).
 * Never apply a raw surface color directly in a component — use this.
 */
export function Surface({ level, className, ...rest }: SurfaceProps) {
  const classes = [LEVEL_CLASS[level], className].filter(Boolean).join(" ");
  return <div data-surface-level={level} className={classes} {...rest} />;
}
