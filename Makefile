.DEFAULT_GOAL := help

ARG := $(word 2,$(MAKECMDGOALS))
CLI := .venv/bin/md-blueprints

$(CLI): pyproject.toml $(shell find src/md_blueprints -type f 2>/dev/null)
	python3 -m venv .venv
	.venv/bin/python -m pip install -e .

# -- Local development --------------------------------------------------------

.PHONY: setup
setup: $(CLI) ## Install CLI, Dive preview dependencies, and create .env from example
	cd .dive-preview && npm install
	@test -f .dive-preview/.env || cp .dive-preview/.env.example .dive-preview/.env
	@echo ""
	@echo "Setup complete. Edit .dive-preview/.env with your MotherDuck token."

.PHONY: install-deploy
install-deploy: ## Install CLI with live MotherDuck deploy dependencies
	python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[deploy]"

.PHONY: preview
preview: ## Preview a blueprint Dive locally (e.g. make preview wikipedia-pageviews)
	@test -n "$(ARG)" || { echo "Usage: make preview <blueprint-name>"; exit 1; }
	@SOURCE="$$( $(CLI) dive-source --blueprints "$(ARG)" $(if $(DIVE),--dive "$(DIVE)") )"; \
	  echo "export { default, REQUIRED_DATABASES } from \"../../$${SOURCE%.tsx}\";" > .dive-preview/src/dive.tsx
	cd .dive-preview && npm run dev

.PHONY: preview-smoke
preview-smoke: ## Build a blueprint Dive preview without starting a dev server
	@test -n "$(ARG)" || { echo "Usage: make preview-smoke <blueprint-name>"; exit 1; }
	@SOURCE="$$( $(CLI) dive-source --blueprints "$(ARG)" $(if $(DIVE),--dive "$(DIVE)") )"; \
	  echo "export { default, REQUIRED_DATABASES } from \"../../$${SOURCE%.tsx}\";" > .dive-preview/src/dive.tsx
	cd .dive-preview && { test -x node_modules/.bin/vite || npm install; }
	cd .dive-preview && npm run build

# -- Scaffolding --------------------------------------------------------------

.PHONY: new-blueprint
new-blueprint: $(CLI) ## Compatibility alias for a complete project blueprint
	@test -n "$(ARG)" || { echo "Usage: make new-blueprint <blueprint-name>"; exit 1; }
	$(CLI) new project "$(ARG)"

.PHONY: new-flight new-dive new-guide new-role new-project
new-flight: $(CLI) ## Scaffold a Flight producer (e.g. make new-flight events-ingest)
	@test -n "$(ARG)" || { echo "Usage: make new-flight <name>"; exit 1; }
	$(CLI) new flight "$(ARG)"

new-dive: $(CLI) ## Scaffold a Dive (e.g. make new-dive events-dashboard INPUT=events-ingest.data)
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

.PHONY: example-smoke
example-smoke: $(CLI) ## Create, validate, build, and destroy a generated blueprint example
	PYTHONDONTWRITEBYTECODE=1 PATH="$(CURDIR)/.venv/bin:$$PATH" ./scripts/scaffold-smoke-test.sh

.PHONY: validate
validate: $(CLI) ## Validate all blueprint manifests without contacting MotherDuck
	PYTHONDONTWRITEBYTECODE=1 $(CLI) validate

.PHONY: render-preview
render-preview: $(CLI) ## Render a blueprint for a preview branch
	@test -n "$(ARG)" || { echo "Usage: make render-preview <blueprint-name>"; exit 1; }
	PYTHONDONTWRITEBYTECODE=1 $(CLI) render --target preview --branch feature/local --blueprints "$(ARG)"

.PHONY: mock-test
mock-test: $(CLI) ## Run local mock deployment tests without contacting MotherDuck
	PYTHONDONTWRITEBYTECODE=1 PATH="$(CURDIR)/.venv/bin:$$PATH" ./scripts/mock-test.sh

.PHONY: package-smoke
package-smoke: ## Build and smoke test the installable md-blueprints package
	PYTHONDONTWRITEBYTECODE=1 ./scripts/package-smoke-test.sh

.PHONY: release-check
release-check: ## Verify package version metadata and optional release tag
	./scripts/check-release-version.sh "$(TAG)"

.PHONY: release-external-check
release-external-check: ## Verify generated-template repository setup for tagged releases
	./scripts/check-release-external-setup.sh

# -- Help ---------------------------------------------------------------------

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

%:
	@:
