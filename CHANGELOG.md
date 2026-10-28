# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]
### Fixed
- Dollar amounts rendered as LaTeX on the live app: two `$` in one answer ("with $768,880. Lodge Queen was second at
  $647,773") lost both signs and showed the words between them as math; the daily alert lost "$50" and "$515". Every
  answer, question, message and alert now goes through `src/display.py` (`$` and HTML escaped, same rule as stage 1);
  report files get `$` escaped only. Found while recording the stage 8 demo on the live app.

## [1.3.0] - 2026-10-26
### Added
- Hotel policy over MCP (`src/policy_mcp.py`, decision 13): a deterministic router, `search_policy` on the stage 7
  server as the manager role with a client allowlist (search_policy only), passages cited, grounded and shown as
  written. Eval split `policy` (5 questions).

## [1.2.0] - 2026-10-25
### Added
- Shared guardrails, tracing and ops log from [hotel-ai-platform](https://github.com/vamsialladev/hotel-ai-platform)
  v0.1.3 (decision 12): input check before any model call, output check against the query's rows, every agent step a
  span, "Reference: ..." on errors, hidden Admin page (`ADMIN_PASSWORD`, shared lockout), JSON startup logs, privacy
  note, `?source=keepawake` runs nothing.
- Red-team suite in CI (`scripts/run_redteam.py`, docs/RED_TEAM.md) and a CycloneDX SBOM artifact.

## [1.1.0] - 2026-10-24

### Added

- Schema retrieval (BM25 over table docs and metric definitions); every answer shows the tables it read and the
  definitions it used. Free `--retrieval` gate in CI.
- Real chat: follow-ups rewritten into a standalone question ("Understood as"), conversation history in the
  browser tab, new conversation, read-only share link with personal data removed, suggested next questions.
- Streamed answers and a "Steps" panel with each step's input and structured result.
- Limits (per session, per minute, daily questions and cost) checked before any model call; a redacted request log.
- Sidebar links: GitHub, portfolio, and the demo video when `DEMO_VIDEO_URL` is set.
- 11 multi-turn eval cases (8 dev, 3 held-out); `--tag` keeps earlier reports.

### Changed

- The full-year alert table loads only when asked (it made every page load slow).
- Dev execution accuracy 98% → 99%, held-out 95% → 100%, p95 4.00 s → 3.52 s, $0.30 → $0.27 per 1,000.

## [1.0.0] - 2026-10-24

### Added

- Synthetic SQLite databases (two seeded years, five planted anomalies each).
- Text-to-SQL agent (Claude Haiku 5.5): clarify / refuse / SQL, a guard (read-only, allowlisted tables, forced
  LIMIT, personal data for managers only, time limit), answers from the rows with ungrounded numbers flagged.
- Daily anomaly check (five SQL rules), Slack incoming webhook or dry run, scheduled GitHub Action.
- Streamlit app: Ask, Daily anomalies, How it works.
- Eval: 60 dev + 10 held-out questions (execution accuracy, clarify, unsafe), 3 runs, saved reports, `--rescore`;
  detector eval on both years.
