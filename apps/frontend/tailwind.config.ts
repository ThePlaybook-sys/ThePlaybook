import type { Config } from "tailwindcss";

// Quant Broadcast / Desk Open design tokens (Volume 5 v5.0 §4).
// Every value below resolves to a CSS custom property defined in
// app/globals.css — Tailwind classes are never a second source of truth
// for a raw color/spacing value.
const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          page: "var(--surface-page)",
          card: "var(--surface-card)",
          elevated: "var(--surface-elevated)",
        },
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          meta: "var(--text-meta)",
        },
        accent: "var(--accent-primary)",
        // rgb()/<alpha-value> (not a bare var()) so opacity modifiers
        // (bg-state-positive/15) actually work -- see globals.css's
        // --state-* comment for why a plain var() silently drops them.
        state: {
          positive: "rgb(var(--state-positive) / <alpha-value>)",
          negative: "rgb(var(--state-negative) / <alpha-value>)",
          neutral: "rgb(var(--state-neutral) / <alpha-value>)",
        },
        team: "var(--team-identity)",
        border: {
          DEFAULT: "var(--border-default)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      fontSize: {
        display: [
          "var(--text-display-size)",
          { lineHeight: "var(--text-display-leading)", fontWeight: "var(--text-display-weight)" },
        ],
        heading: [
          "var(--text-heading-size)",
          { lineHeight: "var(--text-heading-leading)", fontWeight: "var(--text-heading-weight)" },
        ],
        body: ["var(--text-body-size)", { lineHeight: "var(--text-body-leading)" }],
        label: [
          "var(--text-label-size)",
          { lineHeight: "var(--text-label-leading)", letterSpacing: "var(--text-label-tracking)" },
        ],
        data: [
          "var(--text-data-size)",
          { lineHeight: "var(--text-data-leading)", fontWeight: "var(--text-data-weight)" },
        ],
      },
      spacing: {
        xs: "var(--space-xs)",
        sm: "var(--space-sm)",
        md: "var(--space-md)",
        lg: "var(--space-lg)",
        xl: "var(--space-xl)",
        "2xl": "var(--space-2xl)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      transitionDuration: {
        micro: "var(--motion-micro)",
        state: "var(--motion-state)",
      },
    },
  },
  plugins: [],
};

export default config;
