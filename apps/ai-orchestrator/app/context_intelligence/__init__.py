"""Phase 8.1 Contextual Intelligence Foundation Pass (2026-09-08).

A deterministic, sport-agnostic, stateless contextual-intelligence layer
that derives comparable historical context from real data only --
`odds_snapshots`, `weather_snapshots`, `news_article_history`, `venues`/
`games`, the four dimensions Phase 8.0.5's own closeout audit confirmed
REAL + ACTIVE. See `engine.build_contextual_intelligence` for the single
public entry point.

**Not wired into Phase 4's Probability Modeling Agent or any other
committee agent in this pass** -- HQ's explicit instruction is a clean,
importable interface a LATER pass can plug into
`app.agents.probability_modeling.ProbabilityModelingAgent.build_evidence`
(a new `contextual_performance` evidence key, mirroring how `candidate`/
`upstream_findings`/`participation` already reach that function). See
`engine.py`'s own module docstring for the exact integration shape.

**No LLM calls anywhere in this package.** Every dimension builder is a
pure-ish function (I/O only for real Supabase reads, never a model call)
-- matching `app.features.market`/`app.features.market_integrity`'s own
established "deterministic, disclosed, no fabrication" discipline this
package extends rather than replaces."""
