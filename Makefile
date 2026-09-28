# At 42 the home quota is small: put venvs and Python in /goinfre when it exists.
# Elsewhere, let uv use its defaults (.venv in each project).
ifneq ($(wildcard /goinfre),)
GOINFRE  := /goinfre/$(USER)/agent_smith
UV_BASE  := UV_PYTHON_INSTALL_DIR=$(GOINFRE)/uv/python
UV_ENV   := $(UV_BASE) UV_PROJECT_ENVIRONMENT=$(GOINFRE)/.venv
UV_MOU   := $(UV_BASE) UV_PROJECT_ENVIRONMENT=$(GOINFRE)/.venv-moulinette UV_PYTHON=3.12
else
GOINFRE  := .venv moulinette/.venv
UV_BASE  :=
UV_ENV   :=
UV_MOU   := UV_PYTHON=3.12
endif

install:
	$(UV_BASE) uv python install 3.10 3.12
	$(UV_ENV) uv sync
	cd moulinette && $(UV_MOU) uv sync

run:
	$(UV_ENV) uv run python -m agent_smith

debug:
	$(UV_ENV) uv run python -m pdb -m agent_smith

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

fclean: clean
	rm -rf $(GOINFRE)

lint:
	$(UV_ENV) uv run flake8 src
	$(UV_ENV) uv run mypy src --warn-return-any --warn-unused-ignores \
	--ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	$(UV_ENV) uv run flake8 src
	$(UV_ENV) uv run mypy src --warn-return-any --warn-unused-ignores \
	--ignore-missing-imports --disallow-untyped-defs --check-untyped-defs \
	--strict

.PHONY: install run debug clean fclean lint lint-strict
