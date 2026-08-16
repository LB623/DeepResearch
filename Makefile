PYTHON ?= .venv/bin/python
NPM ?= npm
UV ?= uv

.PHONY: diff-check backend-lock backend-test backend-lint backend-typecheck frontend-lint frontend-test frontend-build verify

diff-check:
	git diff --check

backend-lock:
	$(UV) lock --project backend --check

backend-test:
	cd backend && ../$(PYTHON) -m pytest -q

backend-lint:
	cd backend && ../$(PYTHON) -m ruff check src test eval

backend-typecheck:
	cd backend && ../$(PYTHON) -m mypy src

frontend-lint:
	cd frontend && $(NPM) run lint

frontend-test:
	cd frontend && $(NPM) run test

frontend-build:
	cd frontend && $(NPM) run build

verify: diff-check backend-lock backend-test backend-lint backend-typecheck frontend-lint frontend-test frontend-build
