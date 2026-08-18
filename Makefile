.PHONY: db migrate seed yahoo yahoo-watch fred poly dynamics news calendar pack outlook sec yahoo-val valuation scores memos intraday backfill dump restore api web test

db:
	docker compose up -d db

migrate:
	.venv/bin/alembic upgrade head

seed:
	.venv/bin/python -m jobs.seed_tape

yahoo:
	.venv/bin/python -m jobs.ingest_yahoo

fred:
	.venv/bin/python -m jobs.ingest_fred

poly:
	.venv/bin/python -m jobs.ingest_polymarket

dynamics:
	.venv/bin/python -m jobs.compute_dynamics

news:
	.venv/bin/python -m jobs.ingest_news

calendar:
	.venv/bin/python -m jobs.ingest_calendar

pack:
	.venv/bin/python -m jobs.build_pack

outlook:
	.venv/bin/python -m jobs.generate_outlook

sec:
	.venv/bin/python -m jobs.ingest_sec

yahoo-val:
	.venv/bin/python -m jobs.ingest_yahoo --universe valuation

valuation:
	.venv/bin/python -m jobs.compute_valuation

scores:
	.venv/bin/python -m jobs.compute_scores

memos:
	.venv/bin/python -m jobs.generate_memos --template

yahoo-watch:
	.venv/bin/python -m jobs.ingest_yahoo --universe watchlist

intraday:
	.venv/bin/python -m jobs.ingest_intraday

backfill:
	.venv/bin/python -m jobs.backfill yahoo --resume

dump:
	bash scripts/pg_dump.sh

restore:
	bash scripts/pg_restore.sh $(DUMP)

api:
	.venv/bin/uvicorn api.main:app --reload --port 8000

web:
	npm --prefix web run dev

test:
	.venv/bin/pytest
