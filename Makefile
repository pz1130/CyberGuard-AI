# Local verification gate. There is no CI; `make check` is the gate.
#
# The invariants that 04-INVARIANTS.md marks "CI 阻断" (INV-07/08/09/17) are
# enforced as pytest cases in tests/test_invariants_static.py, so `make test`
# already covers them and they also run on a bare `pytest`.

SHELL := /bin/bash
PY := .venv/bin/python
export PYTHONPATH := packages:$(CURDIR)

.PHONY: help check test invariants desktop web-typecheck web-lint web deps clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

check: test web ## Everything: Python suite + invariants + frontend gates
	@echo
	@echo "✓ all checks passed"

test: ## Full pytest suite (needs Postgres+pgvector and Redis — see README)
	$(PY) -m pytest -q

invariants: ## Just the static invariant checks (fast, no services needed)
	$(PY) -m pytest -q tests/test_invariants_static.py

desktop: ## Desktop sidecar suite only
	$(PY) -m pytest -q tests/test_desktop_*.py

web: web-typecheck web-lint ## Frontend gates

web-typecheck: ## webui tsc — must stay clean
	@if [ ! -d webui/node_modules ]; then \
		echo "webui/node_modules missing — run 'make deps'"; exit 2; fi
	cd webui && npx tsc --noEmit -p tsconfig.app.json

web-lint: ## webui eslint — must not regress past scripts/eslint_baseline.json
	$(PY) scripts/eslint_ratchet.py

deps: ## Install frontend dependencies
	npm --prefix webui ci
	npm --prefix apps/desktop ci

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
