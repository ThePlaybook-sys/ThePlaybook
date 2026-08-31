import { Surface, StateBadge, Text } from "@/components/ds";
import { formatDateTime } from "@/app/lib/format";
import { GRADE_LABEL, GRADE_TONE, LegLine, headlineFor } from "@/components/recommendations";
import type {
  RecommendationDetailData,
  RecommendationReconstruction,
  ReconstructionGradeEvent,
  ReconstructionLifecycleEvent,
} from "@/app/lib/api-types";
import { TimeMachineStage } from "./TimeMachineStage";

/**
 * Six-stage Time Machine (Volume 5 v5.0 §5, "all six stages structurally
 * stable" -- HQ Final Decision 3, reaffirmed for M4). Composes two
 * already-authoritative reads, never a third reconstruction engine:
 *
 * - `detail` (GET /v1/recommendations/{displayId}, M2/M3) supplies
 *   Stages 1-3 -- the product/leg identity, Layer 2 evidence, and
 *   Layer 3/4 committee content already built for /recommendations.
 * - `reconstruction` (GET .../reconstruction, M2 proxy to ai-
 *   orchestrator's Milestone 5.3 function) supplies Stages 4-6 -- the
 *   append-only lifecycle/grade/review history no other route exposes.
 *
 * Temporal integrity (HQ's explicit M4 rule): Stage 1 deliberately never
 * renders `detail.status`/`detail.grade` (current, possibly-post-
 * decision facts) -- withdrawal appears only in Stage 4 as a lifecycle
 * event, grading only in Stages 5-6. Nothing here computes an outcome;
 * every badge is a verbatim `outcome` field already written by
 * `app.features.grading`, never re-derived.
 */
export interface TimeMachineProps {
  detail: RecommendationDetailData;
  reconstruction: RecommendationReconstruction;
}

function isPassingType(recommendationType: string): boolean {
  return recommendationType === "no_bet" || recommendationType === "bankroll_preservation";
}

function outcomeBadge(outcome: string): { tone: "positive" | "negative" | "neutral"; label: string } {
  if (outcome in GRADE_LABEL) {
    const key = outcome as keyof typeof GRADE_LABEL;
    return { tone: GRADE_TONE[key], label: GRADE_LABEL[key] };
  }
  // PENDING_MISSING_DATA -- a real, valid leg-level outcome the grading
  // engine writes, but not part of the settled-outcome vocabulary M2.1
  // exposes on the live routes. Rendered honestly, never hidden.
  return { tone: "neutral", label: "Pending" };
}

const LIFECYCLE_EVENT_LABEL: Record<string, string> = {
  ACTIVATED: "Activated",
  WITHDRAWN: "Withdrawn",
  SOFT_DELETED: "Removed",
};

function StageWhatWeRecommended({ detail }: { detail: RecommendationDetailData }) {
  const passing = isPassingType(detail.recommendationType);
  return (
    <TimeMachineStage index={1} title="What We Recommended">
      <Surface level="card" className="flex flex-col gap-sm p-md">
        <Text variant="heading" as="h3">
          {headlineFor(detail)}
        </Text>
        {detail.oneLineSummary && <Text variant="body">{detail.oneLineSummary}</Text>}
        {!passing && detail.legs.length > 0 && (
          <div className="flex flex-col gap-xs border-t border-border-default pt-sm">
            {detail.legs.map((leg) => (
              <LegLine key={`${leg.legOrder}-${leg.marketType}-${leg.selection}`} leg={leg} />
            ))}
          </div>
        )}
      </Surface>
    </TimeMachineStage>
  );
}

function StageWhatWeKnew({
  detail,
  reconstruction,
}: {
  detail: RecommendationDetailData;
  reconstruction: RecommendationReconstruction;
}) {
  const passing = isPassingType(detail.recommendationType);
  const legsWithCommitteeData = passing
    ? []
    : detail.legs.filter((leg) => leg.agentContributions.length > 0 || leg.consensus !== null);

  return (
    <TimeMachineStage index={2} title="What We Knew">
      <Surface level="card" className="flex flex-col gap-sm p-md">
        <Text variant="label">Strategy {reconstruction.strategy_version}</Text>
        <Text variant="label">Decided {formatDateTime(reconstruction.activation_snapshot.activated_at)}</Text>

        {legsWithCommitteeData.length === 0 ? (
          <Text variant="body">No additional evidence recorded.</Text>
        ) : (
          <details>
            <summary className="cursor-pointer text-label text-text-secondary">
              Committee snapshot at decision time
            </summary>
            <div className="mt-sm flex flex-col gap-md">
              {legsWithCommitteeData.map((leg) => (
                <div key={`${leg.legOrder}-${leg.selection}`} className="flex flex-col gap-xs">
                  <Text variant="label">{leg.selection}</Text>
                  {leg.consensus && (
                    <Text variant="body">
                      {leg.consensus.finalAggregateConfidence != null
                        ? `${Math.round(leg.consensus.finalAggregateConfidence * 100)}% final confidence`
                        : null}
                      {leg.consensus.agreementVariance != null
                        ? ` · agreement variance ${leg.consensus.agreementVariance.toFixed(3)}`
                        : ""}
                    </Text>
                  )}
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
              ))}
            </div>
          </details>
        )}
      </Surface>
    </TimeMachineStage>
  );
}

function StageWhyWeLikedIt({ detail }: { detail: RecommendationDetailData }) {
  const passing = isPassingType(detail.recommendationType);
  const legs = passing ? [] : detail.legs;
  const hasProductLevel = Boolean(detail.whyNotOtherShapes) || Boolean(detail.dataLimitations);
  const hasAnything = legs.length > 0 || hasProductLevel;

  return (
    <TimeMachineStage index={3} title="Why We Liked It">
      {!hasAnything && <Text variant="body">No additional evidence recorded.</Text>}
      {legs.length > 0 && (
        <div className="flex flex-col gap-md">
          {legs.map((leg) => (
            <Surface key={`${leg.legOrder}-${leg.selection}`} level="elevated" className="flex flex-col gap-sm p-md">
              <Text variant="label">{leg.selection}</Text>
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
              {leg.wouldChangeMindIf && (
                <div>
                  <Text variant="label">Would change our mind if</Text>
                  <Text variant="body">{leg.wouldChangeMindIf}</Text>
                </div>
              )}
            </Surface>
          ))}
        </div>
      )}
      {hasProductLevel && (
        <Surface level="elevated" className="flex flex-col gap-sm p-md">
          {detail.whyNotOtherShapes && (
            <div>
              <Text variant="label">Why not other shapes</Text>
              <Text variant="body">{detail.whyNotOtherShapes}</Text>
            </div>
          )}
          {detail.dataLimitations && (
            <div>
              <Text variant="label">Data limitations</Text>
              <Text variant="body">{detail.dataLimitations}</Text>
            </div>
          )}
        </Surface>
      )}
    </TimeMachineStage>
  );
}

function StageWhatChanged({ reconstruction }: { reconstruction: RecommendationReconstruction }) {
  const materialEvents = reconstruction.lifecycle_events.filter(
    (event: ReconstructionLifecycleEvent) => event.event_type !== "ACTIVATED",
  );

  return (
    <TimeMachineStage index={4} title="What Changed">
      {materialEvents.length === 0 ? (
        <Text variant="body">No material changes recorded.</Text>
      ) : (
        <ul className="flex flex-col gap-sm">
          {materialEvents.map((event, index) => (
            <li key={`${event.event_type}-${event.event_timestamp}-${index}`}>
              <Surface level="elevated" className="flex flex-col gap-xs p-md">
                <div className="flex items-baseline justify-between gap-md">
                  <Text variant="label">{LIFECYCLE_EVENT_LABEL[event.event_type] ?? event.event_type}</Text>
                  <Text variant="label">{formatDateTime(event.event_timestamp)}</Text>
                </div>
                {event.reason && <Text variant="body">{event.reason}</Text>}
              </Surface>
            </li>
          ))}
        </ul>
      )}
    </TimeMachineStage>
  );
}

function GradeHistoryList({ history }: { history: ReconstructionGradeEvent[] }) {
  return (
    <ul className="flex flex-col gap-sm">
      {history.map((event) => {
        const { tone, label } = outcomeBadge(event.outcome);
        const when = event.computed_at ?? event.graded_at ?? event.created_at;
        return (
          <li key={event.id}>
            <Surface level="elevated" className="flex items-center justify-between gap-md p-md">
              <div className="flex items-center gap-sm">
                <StateBadge tone={tone} label={label} />
                {event.is_correction && <Text variant="label">Correction</Text>}
              </div>
              <Text variant="label">{formatDateTime(when)}</Text>
            </Surface>
          </li>
        );
      })}
    </ul>
  );
}

function StageWhatHappened({ reconstruction }: { reconstruction: RecommendationReconstruction }) {
  const productHistory = reconstruction.product_grade_history;
  const hasMultipleLegs = reconstruction.legs.length > 1;

  return (
    <TimeMachineStage index={5} title="What Happened">
      {productHistory.length === 0 ? (
        <Text variant="body">Awaiting final result.</Text>
      ) : (
        <GradeHistoryList history={productHistory} />
      )}
      {hasMultipleLegs && (
        <details>
          <summary className="cursor-pointer text-label text-text-secondary">Per-leg grading</summary>
          <div className="mt-sm flex flex-col gap-md">
            {reconstruction.legs.map((leg) => (
              <div key={leg.leg.id} className="flex flex-col gap-xs">
                <Text variant="label">{leg.leg.selection}</Text>
                {leg.grade_history.length === 0 ? (
                  <Text variant="body">Awaiting final result.</Text>
                ) : (
                  <GradeHistoryList history={leg.grade_history} />
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </TimeMachineStage>
  );
}

function StageFinalResult({ reconstruction }: { reconstruction: RecommendationReconstruction }) {
  const graded = reconstruction.current_product_grade !== null;
  const reviews = reconstruction.postgame_reviews;
  const latest = reviews.length > 0 ? reviews[reviews.length - 1] : null;
  const hasAgentNotes =
    (latest?.correct_agents && latest.correct_agents.length > 0) ||
    (latest?.underperforming_agents && latest.underperforming_agents.length > 0);

  return (
    <TimeMachineStage index={6} title="Final Result / Review">
      {!graded && <Text variant="body">Awaiting final result.</Text>}
      {graded && !latest && <Text variant="body">Postgame review unavailable.</Text>}
      {latest && (
        <Surface level="elevated" className="flex flex-col gap-sm p-md">
          {latest.outcome_summary && (
            <div>
              <Text variant="label">Outcome</Text>
              <Text variant="body">{latest.outcome_summary}</Text>
            </div>
          )}
          {latest.why_it_won_or_lost && (
            <div>
              <Text variant="label">Why it won or lost</Text>
              <Text variant="body">{latest.why_it_won_or_lost}</Text>
            </div>
          )}
          {latest.learning_notes && (
            <div>
              <Text variant="label">Learning notes</Text>
              <Text variant="body">{latest.learning_notes}</Text>
            </div>
          )}
          {hasAgentNotes && (
            <div className="flex flex-col gap-xs">
              {latest.correct_agents && latest.correct_agents.length > 0 && (
                <Text variant="label">Correct: {latest.correct_agents.join(", ")}</Text>
              )}
              {latest.underperforming_agents && latest.underperforming_agents.length > 0 && (
                <Text variant="label">Underperforming: {latest.underperforming_agents.join(", ")}</Text>
              )}
            </div>
          )}
        </Surface>
      )}
    </TimeMachineStage>
  );
}

export function TimeMachine({ detail, reconstruction }: TimeMachineProps) {
  return (
    <ol className="flex flex-col">
      <StageWhatWeRecommended detail={detail} />
      <StageWhatWeKnew detail={detail} reconstruction={reconstruction} />
      <StageWhyWeLikedIt detail={detail} />
      <StageWhatChanged reconstruction={reconstruction} />
      <StageWhatHappened reconstruction={reconstruction} />
      <StageFinalResult reconstruction={reconstruction} />
    </ol>
  );
}
