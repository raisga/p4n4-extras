# ==============================================================================
# Extras Stack Makefile
# ==============================================================================

.PHONY: help up down restart logs ps clean pull config start stop

# Colors
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RED    := \033[0;31m
BOLD   := \033[1m
DIM    := \033[2m
NC     := \033[0m

# Each service is in a Compose profile of the same name, and nothing starts by
# default: COMPOSE_PROFILES in .env lists the ones to run.
# down/clean also stop services started outside COMPOSE_PROFILES (make start)
ALL_PROFILES := --profile '*'

# Default target
help:
	@echo ""
	@printf "$(BOLD)$(CYAN)  Extras Stack$(NC) - Available Commands (optional services)\n"
	@echo "  ════════════════════════════════════════════"
	@echo ""
	@printf "    $(GREEN)make up$(NC)              Start the services in COMPOSE_PROFILES (none by default)\n"
	@printf "    $(GREEN)make down$(NC)            Stop all services\n"
	@printf "    $(GREEN)make restart$(NC)         Restart all services\n"
	@printf "    $(GREEN)make logs$(NC)            Follow logs for all services\n"
	@printf "    $(GREEN)make ps$(NC)              Docker compose ps\n"
	@printf "    $(GREEN)make pull$(NC)            Pull the images of the services in COMPOSE_PROFILES\n"
	@printf "    $(GREEN)make config$(NC)          Validate docker-compose.yml, its extras and _template/\n"
	@printf "    $(GREEN)make start SERVICE=x$(NC) Start one service, listed in COMPOSE_PROFILES or not\n"
	@printf "    $(GREEN)make stop SERVICE=x$(NC)  Stop one service\n"
	@printf "    $(GREEN)make clean$(NC)           Stop and remove volumes\n"
	@echo ""
	@printf "  $(DIM)Add an extra: copy _template/ (README.md, \"Adding an extra\").$(NC)\n"
	@echo ""

up:
	@if [ -z "$$(docker compose config --services 2>/dev/null)" ]; then \
		printf "$(DIM)  No extras enabled (COMPOSE_PROFILES in .env is empty): nothing to start.$(NC)\n"; \
	else \
		printf "$(YELLOW)  NOTE: p4n4-net must exist. Start p4n4-iot first, or run: docker network create p4n4-net$(NC)\n"; \
		docker compose up -d; \
	fi

down:
	docker compose $(ALL_PROFILES) down

restart:
	docker compose restart

logs:
	docker compose $(ALL_PROFILES) logs -f

ps:
	docker compose $(ALL_PROFILES) ps

pull:
	docker compose pull

config:
	docker compose $(ALL_PROFILES) config --quiet
	docker compose -f _template/docker-compose.yml --env-file _template/.env.example $(ALL_PROFILES) config --quiet
	python3 scripts/check_env_example.py
	@printf "$(GREEN)  docker-compose.yml, its extras and _template/ are valid$(NC)\n"

start:
ifndef SERVICE
	@printf "$(RED)  Usage: make start SERVICE=<name>$(NC)\n"
	@exit 1
endif
	docker compose --profile $(SERVICE) up -d $(SERVICE)

stop:
ifndef SERVICE
	@printf "$(RED)  Usage: make stop SERVICE=<name>$(NC)\n"
	@exit 1
endif
	docker compose $(ALL_PROFILES) stop $(SERVICE)

clean:
	@printf "$(RED)$(BOLD)  WARNING: This will DELETE ALL DATA of the extras services$(NC)\n"
	@read -p "  Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker compose $(ALL_PROFILES) down -v; \
		echo "Cleaned up!"; \
	else \
		echo "Cancelled."; \
	fi
