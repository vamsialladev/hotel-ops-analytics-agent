# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
