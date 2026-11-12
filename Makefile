PYTHON ?= python
.PHONY: dev test
dev:
	cd frontend && npm run dev
test:
	$(PYTHON) scripts/check.py
