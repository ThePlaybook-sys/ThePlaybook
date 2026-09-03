import { Surface, Text } from "@/components/ds";
import { PreviewBadge } from "./PreviewBadge";

const PARLAY_LEGS = [
  "Kansas City Chiefs — Moneyline",
  "Buffalo Bills — Spread -3.5",
  "Under 47.5 — Total",
];

/**
 * Public Web M2.2 -- the mandatory launch-vision visual: a compact
 * MANSA/Telegram conversation surface, not a giant phone mockup and not
 * a generic stock messaging UI. Deliberately non-interactive (`role="img"`
 * on the wrapper, no input, no buttons, no onClick) -- HQ's explicit
 * "do not wire chat/parlay backend behavior yet, do not create fake
 * functional endpoints" boundary. Every piece of this that isn't real
 * today (the conversational interface itself, the parlay result) carries
 * a `PreviewBadge`; nothing here claims to be a live feature.
 *
 * The resulting parlay summary is deliberately numeral-light -- no
 * confidence/EV/price figures, unlike the real `IllustrativeDecisionCard`
 * (which shows that detail because straight-bet recommendations ARE a
 * real, shipped capability today). Showing fabricated combined-parlay
 * math here would overstate how real this capability is; the summary
 * shows only the legs and the discipline (a fourth opportunity
 * deliberately excluded), matching MANSA's real "No Bet" philosophy
 * without implying parlay scoring already works.
 */
export function ConversationalPreview() {
  return (
    <div className="flex flex-col gap-sm" role="img" aria-label="Preview of a MANSA Telegram conversation: a user asks for a 4-leg parlay, MANSA responds that only three legs meet its threshold and shows the resulting 3-leg parlay.">
      <div className="flex items-center justify-between gap-md">
        <Text variant="label" as="span" className="tracking-wide text-mansa-violet">
          MANSA, on Telegram
        </Text>
        <PreviewBadge />
      </div>

      <Surface level="card" className="flex flex-col gap-sm p-md sm:p-lg" aria-hidden="true">
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-lg bg-surface-inset px-md py-sm">
            <Text variant="body" as="p" className="!text-body-bright">
              Build me a 4-leg parlay from Sunday&apos;s strongest opportunities.
            </Text>
          </div>
        </div>

        <div className="flex justify-start">
          <div className="mansa-illuminated-edge-top max-w-[85%] rounded-lg border-t-2 border-t-transparent bg-surface-card px-md py-sm">
            <Text variant="body" as="p" className="!text-body-bright">
              Three legs meet my threshold. I&apos;m leaving the fourth out rather than forcing it.
            </Text>
          </div>
        </div>

        <div className="mt-xs flex flex-col gap-xs rounded-sm border-l-2 border-l-mansa-violet bg-surface-inset p-sm sm:p-md">
          <div className="flex items-center justify-between gap-md">
            <Text variant="label" as="span" className="tracking-wide">
              3-Leg Parlay
            </Text>
            <PreviewBadge label="Preview" />
          </div>
          <ul className="flex flex-col gap-xs">
            {PARLAY_LEGS.map((leg) => (
              <li key={leg}>
                <Text variant="body" as="span" className="!text-body-bright">
                  {leg}
                </Text>
              </li>
            ))}
          </ul>
          <Text variant="label" as="span" className="normal-case text-text-meta">
            A fourth opportunity was evaluated and excluded — not every angle clears MANSA&apos;s bar.
          </Text>
        </div>
      </Surface>
    </div>
  );
}
