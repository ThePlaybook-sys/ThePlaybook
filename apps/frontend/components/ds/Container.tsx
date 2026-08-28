import type { HTMLAttributes } from "react";

export type ContainerProps = HTMLAttributes<HTMLDivElement>;

/**
 * Responsive foundation primitive (Volume 5 v5.0 §8/§10): centers
 * content and applies the mobile-priority → desktop-optimized padding
 * scale. Screens compose this once at their root rather than each
 * re-deriving breakpoint padding independently.
 */
export function Container({ className, ...rest }: ContainerProps) {
  const classes = [
    "mx-auto w-full max-w-3xl px-md sm:px-lg lg:max-w-5xl lg:px-xl",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <div className={classes} {...rest} />;
}
