import { Text } from "@/components/ds";

const STAGES = [
  { label: "Data", sub: "Games, market, situational" },
  { label: "Intelligence & AI Committee", sub: "Organized, then independently evaluated" },
  { label: "MANSA Decision", sub: "One recommendation — or none" },
] as const;

/**
 * Public Web M2.1 -- the one polished visual How It Works needed
 * (HQ's explicit ask: "one visual communicating the intelligence flow:
 * Data -> Intelligence/AI Committee -> MANSA Decision"). A custom,
 * MANSA-native diagram, not stock imagery or generic AI brain/network
 * clipart: three labeled stages connected by a single flowing line,
 * using only the existing Imperial Cobalt palette (dark navy, cobalt,
 * a restrained violet glow on the "Intelligence" stage -- its
 * documented role, "identity/premium depth", per globals.css). The
 * final node is illuminated cobalt (the same `mansa-illuminated-edge`
 * treatment used everywhere else a MANSA decision is shown), never a
 * pulsing/animated "live" indicator -- HQ's explicit "no fake live
 * data" rule. Purely decorative connecting line (`aria-hidden`); the
 * three stage labels themselves carry the real content and remain in
 * the accessibility tree as plain text.
 */
export function IntelligenceFlowDiagram() {
  return (
    <div className="relative flex flex-col items-center gap-lg py-lg sm:flex-row sm:items-start sm:justify-between sm:gap-md">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_center,_rgb(var(--mansa-violet)/0.14),_transparent_65%)]"
      />

      {/* Connecting line -- desktop: horizontal; mobile: vertical. Purely
          decorative, so it's a plain absolutely-positioned div, not an
          SVG needing its own accessible name. */}
      <div
        aria-hidden="true"
        className="absolute left-1/2 top-0 hidden h-full w-px -translate-x-1/2 bg-gradient-to-b from-[rgb(var(--mansa-cobalt)/0.5)] via-[rgb(var(--mansa-violet)/0.5)] to-[rgb(var(--mansa-cobalt)/0.9)] sm:hidden"
      />
      <div
        aria-hidden="true"
        className="absolute left-0 top-6 hidden h-px w-full bg-gradient-to-r from-[rgb(var(--mansa-cobalt)/0.5)] via-[rgb(var(--mansa-violet)/0.5)] to-[rgb(var(--mansa-cobalt)/0.9)] sm:block"
      />

      {STAGES.map((stage, index) => {
        const isFinal = index === STAGES.length - 1;
        return (
          <div key={stage.label} className="relative z-10 flex flex-1 flex-col items-center gap-sm text-center">
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-lg border text-label font-semibold ${
                isFinal
                  ? "mansa-illuminated-edge-top border-t-transparent border-border bg-surface-card text-text-primary"
                  : "border-border bg-surface-card text-text-secondary"
              }`}
            >
              {index + 1}
            </div>
            <div className="flex flex-col gap-xs">
              <Text variant="heading" as="h3" className="text-base">
                {stage.label}
              </Text>
              <Text variant="label" as="span" className="normal-case text-text-meta">
                {stage.sub}
              </Text>
            </div>
          </div>
        );
      })}
    </div>
  );
}
