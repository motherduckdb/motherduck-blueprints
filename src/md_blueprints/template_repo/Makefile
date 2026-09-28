.DEFAULT_GOAL := help

CLI_VERSION := __MD_BLUEPRINTS_VERSION__
CLI := .venv/bin/md-blueprints
CLI_SOURCE := git+https://github.com/motherduckdb/motherduck-blueprints.git@v$(CLI_VERSION)
PYTHON ?= python3
NPM_INSTALL := if [ -f package-lock.json ]; then npm ci; else npm install; fi
export DBT

# Targets that take one package name. Pass it as NAME=<name>; `make <target> <name>` also works.
# Ignore NAME inherited from the shell environment (some systems export it as the hostname).
ifneq ($(filter environment environment override,$(origin NAME)),)
override NAME :=
endif
NAME_TARGETS := preview preview-smoke render-preview new-blueprint new-flight new-dive new-guide new-role new-project
NAME_GOAL := $(firstword $(MAKECMDGOALS))
NAME_WORDS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ifneq ($(filter $(NAME_GOAL),$(NAME_TARGETS)),)
ifneq ($(NAME_WORDS),)
ifneq ($(words $(NAME_WORDS)),1)
$(error make $(NAME_GOAL) takes one name but got "$(NAME_WORDS)". Names are lowercase slugs without spaces, for example make $(NAME_GOAL) NAME=my-package)
endif
ifeq ($(origin NAME),command line)
$(error Pass the name once: make $(NAME_GOAL) NAME=<name> or make $(NAME_GOAL) <name>)
endif
ifneq ($(findstring :,$(NAME_WORDS))$(findstring %,$(NAME_WORDS)),)
$(error "$(NAME_WORDS)" is not a valid name. Names are lowercase slugs using a-z, 0-9, and hyphens)
endif
ifneq ($(filter $(NAME_WORDS),$(shell sed -n 's/^\([a-zA-Z0-9_.-]*\):.*/\1/p' $(lastword $(MAKEFILE_LIST)))),)
$(error "$(NAME_WORDS)" is also a make target. Use make $(NAME_GOAL) NAME=$(NAME_WORDS))
endif
override NAME := $(NAME_WORDS)
# Treat the positional name as a no-op goal so make does not try to build it.
$(eval $(NAME_WORDS):;@:)
endif
endif

# Installer output goes to stderr so commands such as `make guides > brief.md` stay clean.
.PHONY: cli
cli:
	@installed_version="$$( [ -x "$(CLI)" ] && "$(CLI)" --version 2>/dev/null || true )"; \
	  if [ "$$installed_version" != "$(CLI_VERSION)" ]; then \
	    { test -x .venv/bin/python || $(PYTHON) -m venv .venv; } >&2 && \
	    .venv/bin/python -m pip install "md-blueprints @ $(CLI_SOURCE)" >&2; \
	  fi

$(CLI): cli
	@:


.PHONY: setup
setup: $(CLI) ## Install CLI, Dive preview dependencies, and create .env from example
	cd .dive-preview && $(NPM_INSTALL)
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
preview: $(CLI) ## Preview a package Dive locally (NAME=wikipedia-pageviews, optional DIVE=<key>)
	@test -n "$(NAME)" || { echo "Usage: make preview NAME=<blueprint-name> [DIVE=<resource-key>]" >&2; exit 1; }
	@SOURCE="$$( $(CLI) dive-source --blueprints "$(NAME)" $(if $(DIVE),--dive "$(DIVE)") )" && \
	  echo "export { default, REQUIRED_DATABASES } from \"../../$${SOURCE%.tsx}\";" > .dive-preview/src/dive.tsx
	cd .dive-preview && { test -x node_modules/.bin/vite || { $(NPM_INSTALL); }; }
	cd .dive-preview && npm run dev

.PHONY: preview-smoke
preview-smoke: $(CLI) ## Build a package Dive preview without a dev server (NAME=<blueprint-name>)
	@test -n "$(NAME)" || { echo "Usage: make preview-smoke NAME=<blueprint-name> [DIVE=<resource-key>]" >&2; exit 1; }
	@SOURCE="$$( $(CLI) dive-source --blueprints "$(NAME)" $(if $(DIVE),--dive "$(DIVE)") )" && \
	  echo "export { default, REQUIRED_DATABASES } from \"../../$${SOURCE%.tsx}\";" > .dive-preview/src/dive.tsx
	cd .dive-preview && { test -x node_modules/.bin/vite || { $(NPM_INSTALL); }; }
	cd .dive-preview && npm run build


.PHONY: guides init-guides update-guides
guides: $(CLI) ## Print context for your agent to write Guides (optional DBT=/path/to/project)
	@$(CLI) guides $(if $(DBT),--dbt "$$DBT")

init-guides: $(CLI) ## Print an agent brief to initialize Guides (optional DBT=...)
	@$(CLI) guides init $(if $(DBT),--dbt "$$DBT")

update-guides: $(CLI) ## Print an agent brief to update Guides (optional DBT=...)
	@$(CLI) guides update $(if $(DBT),--dbt "$$DBT")

.PHONY: new-blueprint
new-blueprint: $(CLI) ## Deprecated: use make new-project NAME=<name>
	@echo "Deprecation: make new-blueprint will be removed in a future release; use make new-project NAME=<name>." >&2
	@test -n "$(NAME)" || { echo "Usage: make new-project NAME=<name>" >&2; exit 1; }
	$(CLI) new project "$(NAME)"

.PHONY: new-flight new-dive new-guide new-role new-project
new-flight: $(CLI) ## Scaffold a Flight producer (NAME=events-ingest)
	@test -n "$(NAME)" || { echo "Usage: make new-flight NAME=<name>" >&2; exit 1; }
	$(CLI) new flight "$(NAME)"

new-dive: $(CLI) ## Scaffold a Dive (NAME=events-dashboard INPUT=events-ingest.data or URL=<share-url>)
	@test -n "$(NAME)" || { echo "Usage: make new-dive NAME=<name> INPUT=<blueprint.output> or URL=<share-url>" >&2; exit 1; }
	$(CLI) new dive "$(NAME)" $(if $(INPUT),--input "$(INPUT)") $(if $(URL),--url "$(URL)") $(if $(ALIAS),--alias "$(ALIAS)")

new-guide: $(CLI) ## Scaffold a private, disabled Guide (NAME=<name>)
	@test -n "$(NAME)" || { echo "Usage: make new-guide NAME=<name>" >&2; exit 1; }
	$(CLI) new guide "$(NAME)"

new-role: $(CLI) ## Scaffold a production RBAC role, disabled until reviewed (NAME=<name>)
	@test -n "$(NAME)" || { echo "Usage: make new-role NAME=<name>" >&2; exit 1; }
	$(CLI) new role "$(NAME)"

new-project: $(CLI) ## Scaffold a complete Flight + share + Dive project (NAME=<name>)
	@test -n "$(NAME)" || { echo "Usage: make new-project NAME=<name>" >&2; exit 1; }
	$(CLI) new project "$(NAME)"

.PHONY: validate
validate: $(CLI) ## Validate all blueprint manifests without contacting MotherDuck
	PYTHONDONTWRITEBYTECODE=1 $(CLI) validate

.PHONY: render-preview
render-preview: $(CLI) ## Render a package for a preview branch (NAME=<blueprint-name>)
	@test -n "$(NAME)" || { echo "Usage: make render-preview NAME=<blueprint-name>" >&2; exit 1; }
	PYTHONDONTWRITEBYTECODE=1 $(CLI) render --target preview --branch feature/local --blueprints "$(NAME)"

.PHONY: doctor
doctor: $(CLI) ## Check installed CLI, schema status, and upgrade guidance without contacting GitHub
	PYTHONDONTWRITEBYTECODE=1 $(CLI) doctor --offline

.PHONY: upgrade
upgrade: $(CLI) ## Write CLI and action pins for a release and print the diff (VERSION=x.y.z optional)
	PYTHONDONTWRITEBYTECODE=1 $(CLI) upgrade --to "$(or $(VERSION),latest)" --write

.PHONY: migrate
migrate: $(CLI) ## Dry-run schema migration to the latest supported version
	PYTHONDONTWRITEBYTECODE=1 $(CLI) migrate --to latest

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
