# NewsAPI fixture provenance

None of these were captured from a real live call — `newsapi.org` is not on any
verified-reachable allowlist for this sandbox and was not attempted directly
(the pattern established for `the-odds-api.com`, `sportsdata.io`, and
`weatherapi.com` makes a block the reasonable expectation here too). Three
tiers apply, per Mac's 2026-08-11 instruction:

- **CONFIRMED** — verified against the provider's own documentation this
  session. Nothing here reaches this tier — flagged explicitly.
- **ASSUMED** — reflects NewsAPI's long-published public `/v2/everything`
  shape (`status`/`totalResults`/`articles[]` with `source.name`, `title`,
  `description`, `url`, `publishedAt`, `content`), its `{"status":"error",
  "code": ..., "message": ...}` error body shape, and the specific error
  `code` values used here to distinguish auth vs. rate-limit vs. a generic
  bad request on an HTTP 400. Also ASSUMED: the query-construction strategy
  (`"{team} NFL"` vs. bare `"NFL"`) — Volume 2 §8 doesn't specify how a team
  filter should narrow the query, this is this adapter's own reasonable
  choice, not a vendor requirement.
- **DEFERRED LIVE VERIFICATION** — real authentication, the actual live
  payload shape, real quota/rate-limit behavior, real latency, commercial
  usage/retention terms (see the News-persistence deferral rationale in
  `app/adapters/providers/newsapi.py`'s docstring), and a fixture-vs-live
  diff. Tracked centrally in `PROGRESS.md`'s DEFERRED — FINANCIAL/EXTERNAL
  DEPENDENCY checklist, not just here.

## Fixture-by-fixture

| File | Scenario | Tier |
|---|---|---|
| `articles_normal.json` | 3 articles, multiple sources, one with a null `source.id` and one with a null `author` | ASSUMED |
| `articles_empty.json` | zero results, valid structure — no crash on an empty slate | ASSUMED |
| `articles_malformed.json` | article missing required `title`/`url` | N/A — synthetic defect-injection fixture |
| `error_400_bad_key.json` | `code: "apiKeyInvalid"` | ASSUMED |
| `error_400_rate_limited.json` | `code: "rateLimited"` on an HTTP 400 (vs. a direct 429, also handled) | ASSUMED |

## Persistence is explicitly out of scope here

Per Mac's 2026-08-11 instruction, this adapter is tested only through the
normalized-model/cache boundary — no `news_snapshots` table exists or is
proposed in 3C. See the adapter module's own docstring for the full reasoning
(roadmap assigns persistence to Milestone F; NewsAPI-vs-GNews and commercial
storage/retention terms are still unresolved).
