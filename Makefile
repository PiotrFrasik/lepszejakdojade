.PHONY: rebuild up up-otp down logs backend-shell migrate test-backend test-frontend lint

up:
	docker compose up --build

up-otp:
	docker compose --profile otp up --build

down:
	docker compose --profile otp down

logs:
	docker compose logs -f

backend-shell:
	docker compose exec backend bash

migrate:
	docker compose exec backend python manage.py migrate

test-backend:
	docker compose run --rm backend pytest

test-frontend:
	docker compose run --rm frontend npm run test

lint:
	docker compose run --rm backend ruff check .
	docker compose run --rm frontend npm run lint

rebuild:
	docker compose up -d --build -V
