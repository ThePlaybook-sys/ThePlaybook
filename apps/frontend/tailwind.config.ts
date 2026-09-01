import type { Config } from "tailwindcss";

// MANSA Imperial Cobalt design tokens (Volume 5, Phase 6 Milestone 7.2).
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
          page: "rgb(var(--env-000) / <alpha-value>)",
          card: "var(--surface-200)",
          elevated: "var(--surface-300)",
          inset: "var(--surface-inset)",
        },
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          meta: "var(--text-meta)",
        },
        // rgb()/<alpha-value> (not a bare var()) so opacity modifiers
        // (bg-accent/10) actually work -- see globals.css's --mansa-*
        // comment for why a plain var() silently drops them.
        accent: "rgb(var(--mansa-cobalt) / <alpha-value>)",
        mansa: {
          cobalt: "rgb(var(--mansa-cobalt) / <alpha-value>)",
          violet: "rgb(var(--mansa-violet) / <alpha-value>)",
        },
        intel: {
          cyan: "rgb(var(--intel-cyan) / <alpha-value>)",
        },
        attention: {
          amber: "rgb(var(--attention-amber) / <alpha-value>)",
        },
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
        "3xl": "var(--space-3xl)",
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
