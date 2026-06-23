.DEFAULT_GOAL := help

ARG := $(word 2,$(MAKECMDGOALS))

# -- Local development --------------------------------------------------------

.PHONY: setup
setup: ## Install Dive preview dependencies and create .env from example
	cd .dive-preview && npm install
	@test -f .dive-preview/.env || cp .dive-preview/.env.example .dive-preview/.env
	@echo ""
	@echo "Setup complete. Edit .dive-preview/.env with your MotherDuck token."

.PHONY: preview
preview: ## Preview a Dive locally (e.g. make preview revenue-overview)
	@test -n "$(ARG)" || { echo "Usage: make preview <dive-name>"; exit 1; }
	@test -d "dives/$(ARG)" || { echo "Dive folder not found: dives/$(ARG)"; exit 1; }
	@echo 'export { default } from "../../dives/$(ARG)/$(ARG)";' > .dive-preview/src/dive.tsx
	cd .dive-preview && npm run dev

# -- Scaffolding --------------------------------------------------------------

.PHONY: new-dive
new-dive: ## Scaffold a new Dive (e.g. make new-dive revenue-overview)
	@test -n "$(ARG)" || { echo "Usage: make new-dive <dive-name>"; exit 1; }
	@test ! -d "dives/$(ARG)" || { echo "Dive already exists: dives/$(ARG)"; exit 1; }
	mkdir -p dives/$(ARG)
	cp templates/dive/dive_metadata.json dives/$(ARG)/dive_metadata.json
	cp templates/dive/dive.tsx dives/$(ARG)/$(ARG).tsx
	@perl -pi -e 's/__DIVE_NAME__/$(ARG)/g' dives/$(ARG)/dive_metadata.json dives/$(ARG)/$(ARG).tsx
	@echo "Created dives/$(ARG). Register it in .github/workflows/deploy_dives.yaml before CI can deploy it."

.PHONY: new-flight
new-flight: ## Scaffold a new Flight (e.g. make new-flight daily-refresh)
	@test -n "$(ARG)" || { echo "Usage: make new-flight <flight-name>"; exit 1; }
	@test ! -d "flights/$(ARG)" || { echo "Flight already exists: flights/$(ARG)"; exit 1; }
	mkdir -p flights/$(ARG)
	cp templates/flight/flight_metadata.json flights/$(ARG)/flight_metadata.json
	cp templates/flight/flight.py flights/$(ARG)/flight.py
	cp templates/flight/requirements.txt flights/$(ARG)/requirements.txt
	@perl -pi -e 's/__FLIGHT_NAME__/$(ARG)/g' flights/$(ARG)/flight_metadata.json flights/$(ARG)/flight.py
	@echo "Created flights/$(ARG). Register it in .github/workflows/deploy_flights.yaml before CI can deploy it."

.PHONY: validate-flight
validate-flight: ## Validate a Flight folder without contacting MotherDuck
	@test -n "$(ARG)" || { echo "Usage: make validate-flight <flight-name>"; exit 1; }
	./scripts/validate-flight.sh "$(ARG)"

.PHONY: validate-bundle
validate-bundle: ## Validate a bundle without contacting MotherDuck
	@test -n "$(ARG)" || { echo "Usage: make validate-bundle <bundle-name>"; exit 1; }
	./scripts/validate-bundle.sh "$(ARG)"

# -- Help ---------------------------------------------------------------------

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

%:
	@:
