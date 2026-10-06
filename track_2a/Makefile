COACH_PROVIDER ?= apertus
COACH_MODEL ?= llama3:8b
MAX_ANSWERS ?= 12
PROFILE ?=
export COACH_PROVIDER COACH_MODEL PROFILE MAX_ANSWERS

.PHONY: run web web-demo test

run: web

web:
	@sh src/run.sh

web-demo:
	@COACH_PROVIDER=demo sh src/run.sh

test:
	python -m unittest discover -s src/tests -v
