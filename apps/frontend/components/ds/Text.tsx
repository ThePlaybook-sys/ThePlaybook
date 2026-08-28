import type { ElementType, HTMLAttributes } from "react";

type TextVariant = "display" | "heading" | "body" | "label" | "data";

const VARIANT_CLASS: Record<TextVariant, string> = {
  display: "text-display text-text-primary",
  heading: "text-heading text-text-primary",
  body: "text-body text-text-secondary",
  label: "text-label uppercase text-text-meta",
  // tabular-nums: confidence/EV/price must align as a column, never
  // proportionally-spaced digits (Volume 5 v5.0 §4's "data-numeral" role).
  data: "text-data text-text-primary tabular-nums",
};

const DEFAULT_TAG: Record<TextVariant, ElementType> = {
  display: "h1",
  heading: "h2",
  body: "p",
  label: "span",
  data: "span",
};

export type TextProps = HTMLAttributes<HTMLElement> & {
  variant: TextVariant;
  as?: ElementType;
};

/** The five typography roles (Volume 5 v5.0 §4) — never a raw text-size class. */
export function Text({ variant, as, className, ...rest }: TextProps) {
  const Tag = as ?? DEFAULT_TAG[variant];
  const classes = [VARIANT_CLASS[variant], className].filter(Boolean).join(" ");
  return <Tag data-text-variant={variant} className={classes} {...rest} />;
}
