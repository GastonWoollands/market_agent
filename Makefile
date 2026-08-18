.PHONY: db migrate seed yahoo fred poly api web test

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

api:
	.venv/bin/uvicorn api.main:app --reload --port 8000

web:
	npm --prefix web run dev

test:
	.venv/bin/pytest
