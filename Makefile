# Local and CI verification gate for the Docker release.

SHELL := /bin/bash
PY := .venv/bin/python
ALEMBIC := .venv/bin/alembic
export PYTHONPATH := packages:$(CURDIR)

.PHONY: help check rc-check test test-env-up test-env-down invariants web-typecheck web-lint web-audit web-test web deps docker-config docker-build security-scan sbom release-digests source-package clean

RELEASE_IMAGES := cyberguard-api:1.0.0-rc.1 cyberguard-tool-runner:1.0.0-rc.1 cyberguard-webui:1.0.0-rc.1
VERSION ?= 1.0.0-rc.1
REF ?= HEAD

TEST_DATABASE_URL := postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test
TEST_REDIS_URL := redis://:cyberguard-test-only@localhost:56379/0
TEST_ENCRYPTION_KEY := 1111111111111111111111111111111111111111111111111111111111111111
TEST_SECRET_KEY := 2222222222222222222222222222222222222222222222222222222222222222
TEST_ENV := DATABASE_URL=$(TEST_DATABASE_URL) REDIS_URL=$(TEST_REDIS_URL) REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(TEST_ENCRYPTION_KEY) SECRET_KEY=$(TEST_SECRET_KEY) ENVIRONMENT=testing AUTO_APPROVE=false
COMPOSE_CHECK_ENV := CYBERGUARD_ENV_FILE=/dev/null POSTGRES_PASSWORD=compose-check-only REDIS_PASSWORD=compose-check-only RUNNER_TOKEN=compose-check-only BOOTSTRAP_ADMIN_PASSWORD=compose-check-only ENCRYPTION_KEY=$(TEST_ENCRYPTION_KEY) SECRET_KEY=$(TEST_SECRET_KEY)

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

check: test web ## Everything: Python suite + invariants + frontend gates
	@echo
	@echo "✓ all checks passed"

rc-check: check docker-config docker-build security-scan sbom ## Full source-release gate
	@echo
	@echo "✓ release-candidate checks passed"

test: test-env-up ## Full pytest suite against disposable Postgres/Redis
	@set -e; trap '$(MAKE) test-env-down >/dev/null' EXIT; \
		$(TEST_ENV) $(ALEMBIC) -c alembic.ini upgrade head; \
		$(TEST_ENV) $(PY) -m pytest -q

test-env-up: ## Start the isolated test services
	docker compose -f docker-compose.test.yml up -d --wait

test-env-down: ## Remove the isolated test services and data
	docker compose -f docker-compose.test.yml down -v --remove-orphans

invariants: ## Just the static invariant checks (fast, no services needed)
	$(TEST_ENV) $(PY) -m pytest -q tests/test_invariants_static.py

web: web-typecheck web-lint web-audit web-test ## Frontend gates

web-typecheck: ## webui tsc — app and tests must stay clean
	@if [ ! -d webui/node_modules ]; then \
		echo "webui/node_modules missing — run 'make deps'"; exit 2; fi
	cd webui && npx tsc --noEmit -p tsconfig.app.json
	cd webui && npx tsc --noEmit -p tsconfig.test.json

web-lint: ## webui eslint — must not regress past scripts/eslint_baseline.json
	$(PY) scripts/eslint_ratchet.py

web-audit: ## Reject high/critical production dependency advisories
	npm --prefix webui audit --omit=dev --audit-level=high

web-test: ## webui vitest — login, model select, chat stream, thinking, token usage
	@if [ ! -d webui/node_modules ]; then \
		echo "webui/node_modules missing — run 'make deps'"; exit 2; fi
	cd webui && npm test

deps: ## Install frontend dependencies
	npm --prefix webui ci

docker-config: ## Validate the Docker Compose release definition
	$(COMPOSE_CHECK_ENV) docker compose config --quiet

docker-build: ## Build all release images
	$(COMPOSE_CHECK_ENV) docker compose build api tool-runner webui

security-scan: ## Fail on known, fixed High or Critical vulnerabilities in release images
	@for image in $(RELEASE_IMAGES); do \
		docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
			-v cyberguard-trivy-cache:/root/.cache/ \
			aquasec/trivy:0.72.0 image --scanners vuln --severity HIGH,CRITICAL \
			--ignore-unfixed --exit-code 1 $$image || exit $$?; \
	done

release-digests: ## Record local image IDs and registry digests (not-pushed until docker push)
	bash scripts/record_release_digests.sh

source-package: ## Build a source archive and SHA-256 manifest (VERSION=... REF=...)
	VERSION="$(VERSION)" REF="$(REF)" bash scripts/create_source_package.sh

sbom: ## Write CycloneDX SBOMs for the release images to artifacts/
	@mkdir -p artifacts
	@for image in $(RELEASE_IMAGES); do \
		name=$${image%%:*}; \
		docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
			-v "$(CURDIR)/artifacts:/out" anchore/syft:v1.51.1 \
			$$image -o cyclonedx-json=/out/$$name.cdx.json || exit $$?; \
	done

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
