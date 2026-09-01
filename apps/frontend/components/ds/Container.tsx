import type { ElementType, HTMLAttributes } from "react";

export type ContainerProps = HTMLAttributes<HTMLElement> & {
  /** Renders as a `<main>` landmark when a screen's `Container` is that
   * page's primary content region (M7 accessibility pass -- every route
   * needs exactly one `<main>`, distinct from `AppNav`'s `<nav>`).
   * Defaults to `div` for nested/secondary uses. */
  as?: ElementType;
};

/**
 * Responsive foundation primitive (Volume 5 v5.0 §8/§10): centers
 * content and applies the mobile-priority → desktop-optimized padding
 * scale. Screens compose this once at their root rather than each
 * re-deriving breakpoint padding independently.
 */
export function Container({ as, className, ...rest }: ContainerProps) {
  const Tag = as ?? "div";
  const classes = [
    "mx-auto w-full max-w-3xl px-md sm:px-lg lg:max-w-5xl lg:px-xl",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <Tag className={classes} {...rest} />;
}
