import { Surface, Text, StateBadge } from "@/components/ds";
import type { RecommendationDetailData, RecommendationLegDetail } from "@/app/lib/api-types";
import { GradeBadge } from "./GradeBadge";
import { FreshnessLabel } from "./FreshnessLabel";
import { headlineFor, LegLine } from "./RecommendationCard";

interface RejectedAlternative {
  candidateKey?: string;
  selection?: string;
  reasons?: string[];
}

function isRejectedAlternative(value: unknown): value is RejectedAlternative {
  return typeof value === "object" && value !== null;
}

function RejectedAlternativesList({ alternatives }: { alternatives: unknown[] }) {
  const items = alternatives.filter(isRejectedAlternative);
  if (items.length === 0) {
    return null;
  }
  return (
    <ul className="flex flex-col gap-xs">
      {items.map((item, index) => (
        <li key={item.candidateKey ?? index}>
          <Text variant="body" as="span">
            {item.selection ?? "Alternative"}
            {item.reasons && item.reasons.length > 0 ? ` — ${item.reasons.join(", ")}` : ""}
          </Text>
        </li>
      ))}
    </ul>
  );
}

/**
 * Layers 2-4 for one leg (Volume 5 v5.0 §5). The real API attaches
 * evidence/risk/provenance per leg (recommendation_leg_explanations,
 * recommendation_agent_outputs), not flat across the whole product --
 * this composes the same content the Blueprint's idealized layer2/
 * layer3/layer4 shape describes, against the actual per-leg data.
 * Layer 2 (evidence/risk/contributing-agent names) is visible by
 * default; Layer 3 (would-change-mind) and Layer 4 (full provenance,
 * weights, consensus numbers) sit behind native <details> disclosures
 * -- keyboard-accessible without any JS, never shown by default.
 */
function LegDetailSection({ leg }: { leg: RecommendationLegDetail }) {
  return (
    <Surface level="elevated" className="flex flex-col gap-md p-md">
      <LegLine leg={leg} />

      <div className="flex flex-col gap-sm">
        {leg.strongestEvidence && (
          <div>
            <Text variant="label">Strongest evidence</Text>
            <Text variant="body">{leg.strongestEvidence}</Text>
          </div>
        )}
        {leg.biggestRisks && (
          <div>
            <Text variant="label">Biggest risks</Text>
            <Text variant="body">{leg.biggestRisks}</Text>
          </div>
        )}
        {leg.contributingAgents.length > 0 && (
          <div>
            <Text variant="label">Contributing agents</Text>
            <ul className="flex flex-wrap gap-sm">
              {leg.contributingAgents.map((agent) => (
                <li key={agent.name}>
                  <Text variant="label" as="span">
                    {agent.name}
                  </Text>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {leg.wouldChangeMindIf && (
        <details>
          <summary className="cursor-pointer text-label text-text-secondary">Deeper reasoning</summary>
          <div className="mt-sm">
            <Text variant="label">Would change our mind if</Text>
            <Text variant="body">{leg.wouldChangeMindIf}</Text>
          </div>
        </details>
      )}

      {(leg.agentContributions.length > 0 || leg.consensus) && (
        <details>
          <summary className="cursor-pointer text-label text-text-secondary">Full transparency</summary>
          <div className="mt-sm flex flex-col gap-md">
            {leg.consensus && (
              <div className="flex flex-col gap-xs">
                <Text variant="label">Committee consensus</Text>
                {leg.consensus.finalAggregateConfidence != null && (
                  <Text variant="data">
                    {Math.round(leg.consensus.finalAggregateConfidence * 100)}% final confidence
                  </Text>
                )}
                {leg.consensus.agreementVariance != null && (
                  <Text variant="body">
                    Agreement variance {leg.consensus.agreementVariance.toFixed(3)}
                    {leg.consensus.agreementVariance > 0.1 ? " (above the elite reconciliation threshold)" : ""}
                  </Text>
                )}
                {leg.consensus.belowConfidenceFloor && <Text variant="body">Below the confidence floor.</Text>}
              </div>
            )}
            {leg.agentContributions.length > 0 && (
              <div className="flex flex-col gap-xs">
                <Text variant="label">Agent contributions</Text>
                <div className="flex flex-col gap-xs">
                  {leg.agentContributions.map((agent) => (
                    <div key={agent.agentId} className="flex items-baseline justify-between gap-md">
                      <Text variant="body" as="span">
                        {agent.agentName ?? agent.agentId}
                      </Text>
                      <Text variant="label" as="span">
                        {agent.directionalLean ?? "—"} · weight {agent.weightApplied.toFixed(2)}
                        {agent.modelName ? ` · ${agent.modelName}` : ""}
                        {agent.usedFallback ? " (fallback)" : ""}
                      </Text>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </details>
      )}
    </Surface>
  );
}

export interface RecommendationDetailProps {
  recommendation: RecommendationDetailData;
}

export function RecommendationDetail({ recommendation }: RecommendationDetailProps) {
  const isPassing =
    recommendation.recommendationType === "no_bet" || recommendation.recommendationType === "bankroll_preservation";

  const hasProductLayer3 =
    Boolean(recommendation.whyNotOtherShapes) ||
    Boolean(recommendation.dataLimitations) ||
    recommendation.rejectedAlternatives.length > 0;

  return (
    <div className="flex flex-col gap-lg">
      <Surface level="card" className="flex flex-col gap-sm p-lg">
        <div className="flex items-start justify-between gap-md">
          <Text variant="display" as="h1">
            {headlineFor(recommendation)}
          </Text>
          <div className="flex flex-col items-end gap-xs">
            {recommendation.status === "withdrawn" && <StateBadge tone="neutral" label="Withdrawn" />}
            <GradeBadge grade={recommendation.grade} />
          </div>
        </div>
        {recommendation.oneLineSummary && <Text variant="body">{recommendation.oneLineSummary}</Text>}
        {recommendation.status === "withdrawn" && recommendation.withdrawalReason && (
          <Text variant="label">Withdrawn: {recommendation.withdrawalReason}</Text>
        )}
        <FreshnessLabel decidedAt={recommendation.decidedAt} />
      </Surface>

      {!isPassing && recommendation.legs.length > 0 && (
        <div className="flex flex-col gap-md">
          {recommendation.legs.map((leg) => (
            <LegDetailSection key={`${leg.legOrder}-${leg.marketType}-${leg.selection}`} leg={leg} />
          ))}
        </div>
      )}

      {hasProductLayer3 && (
        <details>
          <summary className="cursor-pointer text-label text-text-secondary">Why not another shape</summary>
          <Surface level="elevated" className="mt-sm flex flex-col gap-sm p-md">
            {recommendation.whyNotOtherShapes && (
              <div>
                <Text variant="label">Why not other shapes</Text>
                <Text variant="body">{recommendation.whyNotOtherShapes}</Text>
              </div>
            )}
            {recommendation.rejectedAlternatives.length > 0 && (
              <div>
                <Text variant="label">Rejected alternatives</Text>
                <RejectedAlternativesList alternatives={recommendation.rejectedAlternatives} />
              </div>
            )}
            {recommendation.dataLimitations && (
              <div>
                <Text variant="label">Data limitations</Text>
                <Text variant="body">{recommendation.dataLimitations}</Text>
              </div>
            )}
          </Surface>
        </details>
      )}
    </div>
  );
}
