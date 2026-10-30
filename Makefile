PYTHON ?= python
.PHONY: dev test bootstrap
dev:
	$(PYTHON) scripts/dev.py
test:
	$(PYTHON) scripts/check.py
bootstrap:
	$(PYTHON) scripts/bootstrap.py
