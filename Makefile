GOINFRE  := /goinfre/$(USER)/agent_smith
UV_BASE  := UV_PYTHON_INSTALL_DIR=$(GOINFRE)/uv/python
UV_ENV   := $(UV_BASE) UV_PROJECT_ENVIRONMENT=$(GOINFRE)/.venv
UV_MOU   := $(UV_BASE) UV_PROJECT_ENVIRONMENT=$(GOINFRE)/.venv-moulinette UV_PYTHON=3.12
# GOINFRE  := .venv moulinette/.venv
# UV_BASE  :=
# UV_ENV   :=
# UV_MOU   := UV_PYTHON=3.12

install:
	$(UV_BASE) uv python install 3.10 3.12
	$(UV_ENV) uv sync
	cd moulinette && $(UV_MOU) uv sync --reinstall-package moulinette

docker-up:
	-systemctl --user start podman.socket

run:
	$(UV_ENV) uv run python -m agent_smith

debug:
	$(UV_ENV) uv run python -m pdb -m agent_smith

DOCKER ?= docker

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".vscode" -exec rm -rf {} +
	@# containers left behind by a crashed agent (name set in docker_env.py)
	-$(DOCKER) ps -aq --filter "name=agent_smith_" | xargs -r $(DOCKER) rm -f

fclean: clean
	rm -rf $(GOINFRE)
	rm -rf cache

# NOT in fclean: evaluations/ holds the runs behind BENCHMARK_REPORT.md
clean-evals:
	rm -rf evaluations

# NOT in fclean: SWE-bench images weigh several GB and take long to pull
clean-images:
	-$(DOCKER) images -q "swebench/*" | xargs -r $(DOCKER) rmi -f

lint:
	$(UV_ENV) uv run flake8 src --exclude=src/agent_smith/models.py
	$(UV_ENV) uv run mypy src --warn-return-any --warn-unused-ignores \
	--ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	$(UV_ENV) uv run flake8 src --exclude=src/agent_smith/models.py
	$(UV_ENV) uv run mypy src --warn-return-any --warn-unused-ignores \
	--ignore-missing-imports --disallow-untyped-defs --check-untyped-defs \
	--strict

# Launch interactive sandbox
launch-sandbox:
	$(UV_ENV) uv run sandbox

# With custom configuration
sandbox-config:
	uv run sandbox sandbox_template.json

# With MBPP tools (stdio)
sandbox-mbpp-stdio:
	uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json

# With MBPP tools (HTTP)
sandbox-mbpp-server:
	uv run sandbox --mcp-server <URL>

# With SWE-bench tools
sandbox-swe-bench:
	uv run sandbox --mcp-stdio "python mcp_tools_swebench.py" sandbox_template.json

dump-mbpp:
	mkdir -p cache
	cd moulinette && $(UV_MOU) uv run moulinette_eval dump mbpp \
		--output ../cache/mbpp_task.json

# Exam scripts given by the school
# optional model: make exam-mbpp MODEL=name PROVIDER=https://provider.api/v1
EXAM_ARGS  := --student-path . --moulinette-path moulinette --env-file .env
MODEL_ARGS := $(if $(MODEL),--model-name $(MODEL)) \
	$(if $(PROVIDER),--provider-url $(PROVIDER))

exam-sandbox:
	./exams/exam_sandbox.sh $(EXAM_ARGS)

exam-mbpp: docker-up
	./exams/exam_mbpp.sh $(EXAM_ARGS) $(MODEL_ARGS)

# Rootless Podman (school PCs) cannot copy files owned by our uid into a
# container: run as the namespace root, empty with a real Docker
UNSHARE := $(if $(findstring podman,$(shell docker --version 2>/dev/null)),podman unshare)

exam-swebench: docker-up
	$(UNSHARE) ./exams/exam_swebench.sh $(EXAM_ARGS) $(MODEL_ARGS)

exam-anticheat:
	./exams/exam_anticheat.sh --student-path .

exams: exam-sandbox exam-mbpp exam-anticheat

.PHONY: install run debug clean fclean clean-evals clean-images lint lint-strict
.PHONY: launch-sandbox sandbox-config sandbox-mbpp-stdio sandbox-mbpp-server
.PHONY: sandbox-swe-bench dump-mbpp docker-up
.PHONY: exam-sandbox exam-mbpp exam-swebench exam-anticheat exams
