.DEFAULT_GOAL := help

ARG := $(word 2,$(MAKECMDGOALS))
CLI_VERSION := __MD_BLUEPRINTS_VERSION__
CLI := .venv/bin/md-blueprints
CLI_SOURCE := git+https://github.com/motherduckdb/motherduck-blueprints.git@v$(CLI_VERSION)
PYTHON ?= python3
export DBT

.PHONY: cli
cli:
	@installed_version="$$( [ -x "$(CLI)" ] && "$(CLI)" --version 2>/dev/null || true )"; \
	  if [ "$$installed_version" != "$(CLI_VERSION)" ]; then \
	    { test -x .venv/bin/python || $(PYTHON) -m venv .venv; } && \
	    .venv/bin/python -m pip install "md-blueprints @ $(CLI_SOURCE)"; \
	  fi

$(CLI): cli
	@:

.PHONY: setup
setup: $(CLI) ## Install CLI, Dive preview dependencies, and create .env from example
	cd .dive-preview && npm install
	@test -f .dive-preview/.env || cp .dive-preview/.env.example .dive-preview/.env
	@echo ""
	@echo "Setup complete. Edit .dive-preview/.env with your MotherDuck token."

.PHONY: install-deploy
install-deploy: $(CLI) ## Install the supported MotherDuck CLI for export and live commands
	$(CLI) install-cli

.PHONY: export
export: $(CLI) ## Export all visible Flights, Dives, and Guides as disabled packages (TARGET=prod)
	MD_BLUEPRINTS_SQL_BACKEND=motherduck $(CLI) import --all --target "$(or $(TARGET),prod)" --write

.PHONY: preview
preview: $(CLI) ## Preview a blueprint Dive locally (e.g. make preview wikipedia-pageviews)
	@test -n "$(ARG)" || { echo "Usage: make preview <blueprint-name>"; exit 1; }
	@SOURCE="$$( $(CLI) dive-source --blueprints "$(ARG)" $(if $(DIVE),--dive "$(DIVE)") )" && \
	  echo "export { default, REQUIRED_DATABASES } from \"../../$${SOURCE%.tsx}\";" > .dive-preview/src/dive.tsx
	cd .dive-preview && npm run dev

.PHONY: preview-smoke
preview-smoke: $(CLI) ## Build a blueprint Dive preview without starting a dev server
	@test -n "$(ARG)" || { echo "Usage: make preview-smoke <blueprint-name>"; exit 1; }
	@SOURCE="$$( $(CLI) dive-source --blueprints "$(ARG)" $(if $(DIVE),--dive "$(DIVE)") )" && \
	  echo "export { default, REQUIRED_DATABASES } from \"../../$${SOURCE%.tsx}\";" > .dive-preview/src/dive.tsx
	cd .dive-preview && { test -x node_modules/.bin/vite || npm install; }
	cd .dive-preview && npm run build

.PHONY: guides init-guides update-guides
guides: $(CLI) ## Gather context for your agent to write Guides (optional DBT=/path/to/project)
	$(CLI) guides $(if $(DBT),--dbt "$$DBT")

init-guides: $(CLI) ## Gather an agent brief to initialize Guides
	$(CLI) guides init $(if $(DBT),--dbt "$$DBT")

update-guides: $(CLI) ## Gather an agent brief to update Guides
	$(CLI) guides update $(if $(DBT),--dbt "$$DBT")

.PHONY: new-blueprint
new-blueprint: $(CLI) ## Compatibility alias for a complete project blueprint
	@test -n "$(ARG)" || { echo "Usage: make new-blueprint <blueprint-name>"; exit 1; }
	$(CLI) new project "$(ARG)"

.PHONY: new-flight new-dive new-guide new-role new-project
new-flight: $(CLI) ## Scaffold a Flight producer
	@test -n "$(ARG)" || { echo "Usage: make new-flight <name>"; exit 1; }
	$(CLI) new flight "$(ARG)"

new-dive: $(CLI) ## Scaffold a Dive using INPUT=<blueprint.output> or URL=<share-url>
	@test -n "$(ARG)" || { echo "Usage: make new-dive <name> INPUT=<blueprint.output> or URL=<share-url>"; exit 1; }
	$(CLI) new dive "$(ARG)" $(if $(INPUT),--input "$(INPUT)") $(if $(URL),--url "$(URL)") $(if $(ALIAS),--alias "$(ALIAS)")

new-guide: $(CLI) ## Scaffold a Guide
	@test -n "$(ARG)" || { echo "Usage: make new-guide <name>"; exit 1; }
	$(CLI) new guide "$(ARG)"

new-role: $(CLI) ## Scaffold a production RBAC role
	@test -n "$(ARG)" || { echo "Usage: make new-role <name>"; exit 1; }
	$(CLI) new role "$(ARG)"

new-project: $(CLI) ## Scaffold a complete Flight + share + Dive project
	@test -n "$(ARG)" || { echo "Usage: make new-project <name>"; exit 1; }
	$(CLI) new project "$(ARG)"

.PHONY: validate
validate: $(CLI) ## Validate all blueprint manifests without contacting MotherDuck
	PYTHONDONTWRITEBYTECODE=1 $(CLI) validate

.PHONY: render-preview
render-preview: $(CLI) ## Render a blueprint for a preview branch
	@test -n "$(ARG)" || { echo "Usage: make render-preview <blueprint-name>"; exit 1; }
	PYTHONDONTWRITEBYTECODE=1 $(CLI) render --target preview --branch feature/local --blueprints "$(ARG)"

.PHONY: doctor
doctor: $(CLI) ## Check installed CLI, schema status, and upgrade guidance
	PYTHONDONTWRITEBYTECODE=1 $(CLI) doctor --offline

.PHONY: migrate
.PHONY: upgrade
upgrade: $(CLI) ## Update CLI and action pins together, then show the diff (VERSION=x.y.z optional)
	PYTHONDONTWRITEBYTECODE=1 $(CLI) upgrade --to "$(or $(VERSION),latest)" --write

migrate: $(CLI) ## Dry-run schema migration to the latest supported version
	PYTHONDONTWRITEBYTECODE=1 $(CLI) migrate --to latest

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

%:
	@:
