.PHONY: rebuild up up-otp down logs backend-shell migrate test-backend test-frontend lint otp-build otp-up otp-down

# Supported OTP cities (must match the otp-<city> / otp-build-<city> compose services).
OTP_CITIES := krakow warszawa
space := $(subst ,, )
# CITY=<city> selects one city; empty means all (otp-up, otp-down). otp-build requires it.
CITY ?=
ifneq ($(CITY),)
$(if $(filter $(CITY),$(OTP_CITIES)),,$(error Unknown CITY '$(CITY)'; expected one of: $(OTP_CITIES)))
endif
OTP_SELECTED := $(if $(CITY),$(CITY),$(OTP_CITIES))

up:
	docker compose up --build

# Whole stack plus OTP for both cities. Needs graphs from `make otp-build`.
up-otp:
	docker compose --profile otp up --build

down:
	docker compose --profile otp --profile otp-build down

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

# Start only the OTP services (all cities, or CITY=<city>) in the background.
# Cities without a built graph (otp/data/<city>/graph.obj) are skipped to avoid crash loops.
otp-up:
	@for c in $(OTP_SELECTED); do \
		mkdir -p otp/data/$$c; \
		if [ -f otp/data/$$c/graph.obj ]; then \
			docker compose --profile otp up -d otp-$$c; \
		else \
			echo "WARNING: otp/data/$$c/graph.obj missing, skipping otp-$$c (run: make otp-build CITY=$$c)"; \
		fi; \
	done

otp-down:
	docker compose --profile otp stop $(foreach c,$(OTP_SELECTED),otp-$(c))

# Prepare OTP inputs (GTFS + clipped OSM + configs) in the backend container, build the
# graph, then restart that city's OTP service if it is running.
# Usage: make otp-build CITY=krakow
# MEMORY: peak ~3.5 GB (krakow) / ~7.4 GB (warszawa). Build ONE city at a time, never in parallel.
# PERMISSIONS: the prepare step runs as the host user so files in otp/data/<city> stay
# yours on Linux; the OTP container runs as root, so graph.obj may be root-owned there.
otp-build:
	@test -n "$(CITY)" || { echo "Usage: make otp-build CITY=$(subst $(space),|,$(OTP_CITIES))"; exit 1; }
	mkdir -p otp/data/$(CITY)
	docker compose run --rm --user "$$(id -u):$$(id -g)" backend python manage.py prepare_otp_inputs --city $(CITY)
	docker compose --profile otp-build run --rm otp-build-$(CITY)
	@if [ -n "$$(docker compose --profile otp ps -q --status running otp-$(CITY))" ]; then \
		echo "Restarting otp-$(CITY) to load the new graph"; \
		docker compose --profile otp restart otp-$(CITY); \
	fi
