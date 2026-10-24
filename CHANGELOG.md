# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-24

### Added

- Synthetic SQLite databases (two seeded years, five planted anomalies each).
- Text-to-SQL agent (Claude Haiku 5.5): clarify / refuse / SQL, a guard (read-only, allowlisted tables, forced
  LIMIT, personal data for managers only, time limit), answers from the rows with ungrounded numbers flagged.
- Daily anomaly check (five SQL rules), Slack incoming webhook or dry run, scheduled GitHub Action.
- Streamlit app: Ask, Daily anomalies, How it works.
- Eval: 60 dev + 10 held-out questions (execution accuracy, clarify, unsafe), 3 runs, saved reports, `--rescore`;
  detector eval on both years.
