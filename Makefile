.DEFAULT_GOAL := help

ARG := $(word 2,$(MAKECMDGOALS))
DB_NAME := $(subst -,_,$(ARG))

# -- Local development --------------------------------------------------------

.PHONY: setup
setup: ## Install Dive preview dependencies and create .env from example
	cd .dive-preview && npm install
	@test -f .dive-preview/.env || cp .dive-preview/.env.example .dive-preview/.env
	@echo ""
	@echo "Setup complete. Edit .dive-preview/.env with your MotherDuck token."

.PHONY: preview
preview: ## Preview a blueprint Dive locally (e.g. make preview wikipedia-pageviews)
	@test -n "$(ARG)" || { echo "Usage: make preview <blueprint-name>"; exit 1; }
	@test -f "blueprints/$(ARG)/src/dive.tsx" || { echo "Dive source not found: blueprints/$(ARG)/src/dive.tsx"; exit 1; }
	@echo 'export { default } from "../../blueprints/$(ARG)/src/dive";' > .dive-preview/src/dive.tsx
	cd .dive-preview && npm run dev

.PHONY: preview-smoke
preview-smoke: ## Build a blueprint Dive preview without starting a dev server
	@test -n "$(ARG)" || { echo "Usage: make preview-smoke <blueprint-name>"; exit 1; }
	@test -f "blueprints/$(ARG)/src/dive.tsx" || { echo "Dive source not found: blueprints/$(ARG)/src/dive.tsx"; exit 1; }
	@echo 'export { default } from "../../blueprints/$(ARG)/src/dive";' > .dive-preview/src/dive.tsx
	cd .dive-preview && { test -x node_modules/.bin/vite || npm install; }
	cd .dive-preview && npm run build

# -- Scaffolding --------------------------------------------------------------

.PHONY: new-blueprint
new-blueprint: ## Scaffold a new blueprint package (e.g. make new-blueprint revenue-overview)
	@test -n "$(ARG)" || { echo "Usage: make new-blueprint <blueprint-name>"; exit 1; }
	@printf '%s\n' "$(ARG)" | grep -Eq '^[a-z0-9][a-z0-9-]*$$' || { echo "Blueprint name must be a lowercase slug: a-z, 0-9, and hyphen"; exit 1; }
	@test ! -d "blueprints/$(ARG)" || { echo "Blueprint already exists: blueprints/$(ARG)"; exit 1; }
	mkdir -p blueprints/$(ARG)/src
	cp templates/blueprint/blueprint.yml blueprints/$(ARG)/blueprint.yml
	cp templates/blueprint/flight.py blueprints/$(ARG)/src/flight.py
	cp templates/blueprint/requirements.txt blueprints/$(ARG)/src/requirements.txt
	cp templates/blueprint/dive.tsx blueprints/$(ARG)/src/dive.tsx
	@perl -pi -e 's/__BLUEPRINT_NAME__/$(ARG)/g; s/__DATABASE_NAME__/$(DB_NAME)/g' blueprints/$(ARG)/blueprint.yml blueprints/$(ARG)/src/flight.py blueprints/$(ARG)/src/dive.tsx
	@echo "Created blueprints/$(ARG). Run make validate before opening a PR."

.PHONY: validate
validate: ## Validate all blueprint manifests without contacting MotherDuck
	./tools/md_blueprints validate

.PHONY: render-preview
render-preview: ## Render a blueprint for a preview branch
	@test -n "$(ARG)" || { echo "Usage: make render-preview <blueprint-name>"; exit 1; }
	./tools/md_blueprints render --target preview --branch feature/local --blueprints "$(ARG)"

.PHONY: mock-test
mock-test: ## Run local mock deployment tests without contacting MotherDuck
	./scripts/mock-test.sh

# -- Help ---------------------------------------------------------------------

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

%:
	@:
