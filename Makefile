PYTHON ?= python
.PHONY: dev test test-browser bootstrap
dev:
	$(PYTHON) scripts/dev.py
test:
	$(PYTHON) scripts/check.py
test-browser:
	$(PYTHON) scripts/check.py --browser
bootstrap:
	$(PYTHON) scripts/bootstrap.py
