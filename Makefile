.PHONY: check lint test gates app daily db

check: lint test gates

lint:
	ruff check .
	ruff format --check .

test:
	python -m pytest --cov --cov-fail-under=80

gates:
	python -m eval.run_eval --guard-only
	python -m eval.run_eval --retrieval
	python -m eval.run_anomaly_eval --gate

app:
	streamlit run app.py

daily:
	python scripts/daily_check.py

db:
	python scripts/make_db.py && python scripts/make_db.py --heldout
