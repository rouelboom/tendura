.PHONY: sync check test

sync:
	UV_PROJECT_ENVIRONMENT=.venv uv sync --python 3.13.9 --no-dev

check:
	.venv/bin/python -m compileall -q tendura tests

test:
	.venv/bin/python -m unittest discover -s tests -v
