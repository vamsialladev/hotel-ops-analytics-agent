# Contributing

1. Branch from `main`, open a pull request; CI must pass. Commits follow
   [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
2. **Schema or definitions:** change `src/schema.py`; if a table is added, the guard's allowlist follows
   automatically. Add eval questions with reference SQL, run `python -m eval.run_eval --guard-only`.
3. **Prompt changes:** run the dev eval (3 runs) before and after, put both numbers in the PR. Run the held-out
   set only once you're done changing things.
4. **A new anomaly rule:** add it to `src/anomaly.py` (`RULES`), plant an example in `scripts/make_db.py` for both
   seeds, rebuild, and run `python -m eval.run_anomaly_eval`.
5. Run `make check` before pushing.
