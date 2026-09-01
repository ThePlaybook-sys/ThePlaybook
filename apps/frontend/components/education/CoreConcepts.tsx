import { Surface, Text } from "@/components/ds";

interface Concept {
  term: string;
  definition: string;
}

/** The four concepts HQ's M6 authorization requires at minimum, kept to
 * the exact careful wording given -- especially that CONFIDENCE is
 * explicitly NOT the probability of winning, a distinction this
 * codebase's own agent committee (Volume 4) depends on the user not
 * confusing. Reused verbatim by both onboarding's first-use education
 * and Account's "How MANSA Works". Deliberately brand-name-agnostic --
 * these four definitions never hardcode "MANSA" (or, before M7's brand
 * alignment, "The Playbook") inline, since the product name is set by
 * the surrounding page, not repeated inside every reused fragment. */
const CONCEPTS: Concept[] = [
  {
    term: "Confidence",
    definition:
      "How strongly the AI committee agrees on a recommendation. This is not automatically the probability that the wager wins.",
  },
  {
    term: "Modeled Probability",
    definition:
      "The system's own estimate of how likely the outcome is, where the data supports making that estimate.",
  },
  {
    term: "EV",
    definition: "Estimated value -- how favorable a recommendation looks relative to the market price.",
  },
  {
    term: "No Bet",
    definition:
      "A legitimate recommendation on its own, not a failure to find one. It means the system didn't find a play that cleared its bar today.",
  },
];

export interface CoreConceptsProps {
  /** Show only the term/definition list (onboarding's compact first-use
   * pass) vs. the fuller heading treatment (Account's own page). */
  compact?: boolean;
}

export function CoreConcepts({ compact = false }: CoreConceptsProps) {
  return (
    <div className="flex flex-col gap-md">
      {!compact && (
        <Text variant="heading" as="h2">
          The Basics
        </Text>
      )}
      <div className="flex flex-col gap-sm">
        {CONCEPTS.map((concept) => (
          <Surface key={concept.term} level="card" className="flex flex-col gap-xs p-md">
            <Text variant="label" as="span">
              {concept.term}
            </Text>
            <Text variant="body">{concept.definition}</Text>
          </Surface>
        ))}
      </div>
    </div>
  );
}
