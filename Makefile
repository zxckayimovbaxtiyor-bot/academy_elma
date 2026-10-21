# Common operations. Everything goes through docker compose.
VERSION ?= dev
COMPOSE := docker compose

.PHONY: help build up down logs seed demo-seed admin test bundle

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

build: ## build the app images
	APP_VERSION=$(VERSION) $(COMPOSE) build

up: ## start postgres, api, worker and nginx
	APP_VERSION=$(VERSION) $(COMPOSE) up -d

down: ## stop everything (data volumes are kept)
	$(COMPOSE) down

logs: ## follow logs
	$(COMPOSE) logs -f --tail=100

seed: ## load reference data (course, regions, job roles, modules)
	$(COMPOSE) exec api python -m app.cli seed

demo-seed: ## reference data + synthetic branches/people/wave (demo only): make demo-seed PASSWORD=...
	$(COMPOSE) exec api python -m app.cli seed --synthetic --password "$(PASSWORD)"

admin: ## bootstrap an admin: make admin ID=ADM-0001 NAME="Full Name"
	$(COMPOSE) exec api python -m app.cli create-admin --employee-id "$(ID)" --full-name "$(NAME)"

test: ## run pytest in the api image against a throwaway academy_test database
	$(COMPOSE) run --rm api sh -c 'TEST_DATABASE_URL="$${DATABASE_URL%/*}/academy_test" pytest -q'

bundle: ## build images and save them for an offline server: dist/academy-$(VERSION).tar
	APP_VERSION=$(VERSION) $(COMPOSE) build
	docker pull postgres:16
	mkdir -p dist
	docker save -o dist/academy-$(VERSION).tar academy-api:$(VERSION) academy-web:$(VERSION) postgres:16
	@echo "Copy dist/academy-$(VERSION).tar, docker-compose.yml and .env to the server, then:"
	@echo "  docker load -i academy-$(VERSION).tar && APP_VERSION=$(VERSION) docker compose up -d"
