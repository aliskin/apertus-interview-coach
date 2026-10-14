COACH_PROVIDER ?= apertus
PYTHON ?= python3
REVIEW_PORT ?= 8081
WEB_PORT ?= 8080
COACH_MODEL ?= llama3:8b
MAX_ANSWERS ?= 12
PROFILE ?=
export COACH_PROVIDER COACH_MODEL PROFILE MAX_ANSWERS WEB_PORT

.PHONY: run web web-demo review review-demo test

run: web

web:
	@sh src/run.sh

web-demo:
	@COACH_PROVIDER=demo sh src/run.sh

review:
	$(PYTHON) src/review/portal.py --port $(REVIEW_PORT)

review-demo:
	$(PYTHON) src/review/prepare.py --demo
	$(PYTHON) src/review/portal.py --port $(REVIEW_PORT)

test:
	$(PYTHON) -m unittest discover -s src/tests -v
