.PHONY: up down build logs migrate seed test test-backend fmt-check

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.scripts.seed_demo

test:
	docker compose exec -e DATABASE_URL=$${TEST_DATABASE_URL:-postgresql+psycopg://buildgate:buildgate@db:5432/buildgate_test} api pytest -v
