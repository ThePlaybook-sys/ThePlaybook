"""News contextual dimension (Phase 8.1 Foundation Pass, 2026-09-08).
Real data source: `news_article_history`, real and active since Phase
8.0.5 Pass 2.2 (durable poll state, 80/day hard ceiling, 4-hour cadence).

**"Similarity" means something different here than in the weather/market
dimensions, and that difference is disclosed, not hidden.** There is no
natural numeric distance between two news articles the way there is
between two temperature readings. This dimension instead reports the
fraction of a team's real captured articles that fall within
`app.features.market_integrity.EXPLANATORY_EVIDENCE_LOOKBACK` of any real
market-movement window for this game -- a genuine "how much of this
team's real news activity temporally clusters with real market
movement" measure, reusing the exact same lookback window and pure
`movement_windows` computation Milestone 7.1 already established, never
a second, differently-tuned window invented here.

**Category/type is explicitly NOT supported.** `news_article_history`
carries no category/type column (`provider_name`, `article_url`,
`published_at`, `headline`, `summary`, `source_name`, `related_team_ids`
-- the complete real schema, Volume 3 §4.4). Classifying a headline into
a category would require either an LLM call (forbidden in this engine)
or a hand-rolled keyword heuristic (a real risk of silent
misclassification this project's own no-fabrication discipline does not
accept) -- so this sub-facet is honestly declared unsupported rather than
guessed at.

**Never infers causation from temporal proximity (HQ's explicit
instruction, restated in every result this dimension produces, not just
this docstring).**"""
from __future__ import annotations

from datetime import datetime, timezone

from app.context_intelligence.models import ContextualDimensionResult, ProvenanceRef
from app.context_intelligence.scoring import MIN_SAMPLE_FOR_FULL_CONFIDENCE, parse_ts, recency_weight
from app.features.market_integrity import EXPLANATORY_EVIDENCE_LOOKBACK, movement_windows

_STANDING_CONFOUNDER = (
    "No real completed-game outcome data exists for any tracked game yet -- this describes real "
    "news activity and its temporal relationship to real market movement only, never a predictive "
    "or outcome-linked claim."
)
_CAUSATION_CONFOUNDER = (
    "Temporal proximity to a market movement is NOT evidence of causation -- an article observed "
    "near a movement window is reported as a real, timestamped co-occurrence only."
)
_CATEGORY_CONFOUNDER = (
    "Article category/type is not supported -- news_article_history carries no category column, "
    "and this engine performs no LLM or heuristic classification of headline content."
)

_CONTEXT_DIMENSIONS_USED = ("published_at", "ingested_at", "market_movement_proximity")


def _near_any_window(ts: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    for start, end in windows:
        if start - EXPLANATORY_EVIDENCE_LOOKBACK <= ts <= end:
            return True
    return False


def compute_news_context(
    *,
    game_id: str,
    news_articles_for_teams: list[dict],
    target_odds_snapshots: list[dict] = (),
    now: datetime | None = None,
) -> ContextualDimensionResult:
    """Pure function over already-fetched rows -- no I/O, directly
    unit-testable. `news_articles_for_teams` is the real, already
    team-filtered article list (via the existing `app.persistence.
    market_integrity.read_news_article_history_for_teams`);
    `target_odds_snapshots` is this game's own `odds_snapshots` history,
    used only to locate real movement windows for the proximity check."""
    now = now or datetime.now(timezone.utc)
    sample_size = len(news_articles_for_teams)

    if sample_size == 0:
        return ContextualDimensionResult(
            dimension="news",
            context_dimensions_used=(),
            sample_size=0,
            similarity_score=None,
            recency_weighting=None,
            confidence=None,
            confounders=(_STANDING_CONFOUNDER, _CAUSATION_CONFOUNDER, _CATEGORY_CONFOUNDER),
            insufficient_evidence=True,
            insufficient_evidence_reason="no real news_article_history rows exist for this game's teams yet",
            provenance=(ProvenanceRef(table="news_article_history", source="gnews", row_count=0, earliest_at=None, latest_at=None),),
            facts={},
        )

    windows = list(movement_windows(list(target_odds_snapshots)).values()) if target_odds_snapshots else []

    article_facts = []
    near_count = 0
    weights = []
    for row in news_articles_for_teams:
        raw_ts = row.get("ingested_at") or row.get("published_at")
        ts = parse_ts(raw_ts) if raw_ts else None
        near = _near_any_window(ts, windows) if ts is not None and windows else False
        if near:
            near_count += 1
        if ts is not None:
            weights.append(recency_weight(ts, now=now))
        article_facts.append(
            {
                "headline": row.get("headline"),
                "source_name": row.get("source_name"),
                "published_at": row.get("published_at"),
                "ingested_at": row.get("ingested_at"),
                "near_market_movement_window": near,
            }
        )

    timestamps = sorted(
        parse_ts(row["ingested_at"] or row["published_at"])
        for row in news_articles_for_teams
        if row.get("ingested_at") or row.get("published_at")
    )
    provenance = (
        ProvenanceRef(
            table="news_article_history",
            source="gnews",
            row_count=sample_size,
            earliest_at=timestamps[0].isoformat() if timestamps else None,
            latest_at=timestamps[-1].isoformat() if timestamps else None,
        ),
    )

    # "Similarity" for News = the fraction of this team's real articles
    # that temporally cluster with a real market-movement window -- see
    # module docstring's explicit reframing.
    similarity = near_count / sample_size if sample_size else None
    avg_recency = sum(weights) / len(weights) if weights else 0.0

    facts = {
        "articles_considered": article_facts,
        "articles_near_market_movement": near_count,
        "market_movement_windows_checked": len(windows),
    }

    if not windows:
        confounders = (
            _STANDING_CONFOUNDER,
            _CAUSATION_CONFOUNDER,
            _CATEGORY_CONFOUNDER,
            "no real odds_snapshots history exists for this game yet, so market-movement proximity could not be checked",
        )
    else:
        confounders = (_STANDING_CONFOUNDER, _CAUSATION_CONFOUNDER, _CATEGORY_CONFOUNDER)

    return ContextualDimensionResult(
        dimension="news",
        context_dimensions_used=_CONTEXT_DIMENSIONS_USED,
        sample_size=sample_size,
        similarity_score=round(similarity, 4) if similarity is not None else None,
        recency_weighting=round(avg_recency, 4),
        confidence=round(min(1.0, sample_size / MIN_SAMPLE_FOR_FULL_CONFIDENCE) * avg_recency, 4),
        confounders=confounders,
        insufficient_evidence=False,
        insufficient_evidence_reason=None,
        provenance=provenance,
        facts=facts,
    )


__all__ = ["compute_news_context"]
