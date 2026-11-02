import argparse
import os
import signal
from pathlib import Path
from agent_smith.llm.client import LLMClient
from agent_smith.llm.config import LLMConfig
import sys
import time
from dotenv import load_dotenv
from mcp import StdioServerParameters
from agent_smith.sandbox.manual import build_manual
from agent_smith.sandbox.mcp_bridge import McpBridge
from agent_smith.agent.loop import AgentRun, run_agent
from agent_smith.models import SolutionOutput, SWEBenchTaskInput
from agent_smith.sandbox.cli import load_config
from agent_smith.sandbox.sandbox import Sandbox
from agent_smith.swebench.docker_env import Container


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "qwen/qwen3.8-27b"
DEFAULT_PROVIDER_URL = "https://api.groq.com/openai/v1"

DEADLINE_SECONDS = 840      # limit 900 s
MAX_ITERATIONS = 25         # limit 30
MAX_INPUT_TOKENS = 300_000
MAX_OUTPUT_TOKENS = 10_000
EVAL_PATH = "/tmp/agent/eval.sh"
# variables the tool server needs to reach Docker (see TOOL_ENV_VARS)
DOCKER_ENV_VARS = ("DOCKER_CMD", "DOCKER_HOST", "TEST_OUTPUT",
                   "XDG_RUNTIME_DIR")
# CONTAINER_SETUP, plus Podman's own settings: without _CONTAINERS_*,
# rootless Podman run under `podman unshare` thinks it is root
DOCKER_ENV_PREFIXES = ("CONTAINER", "_CONTAINERS")

SYSTEM_RULES = """You are an expert software engineer fixing a real bug in \
the repository at /testbed. Your Python code runs in a sandbox: use the \
functions listed below to explore and edit the repository.

Answer format, every turn:
Thought: one or two sentences.
```python
<your code>
```<end_code>

Method:
1. Locate: search_code and search_function_or_class_definition_in_code
   to find the code involved, then read_file the relevant lines.
2. Reproduce: run_command a short Python snippet that shows the bug.
3. Fix: edit_file with a minimal change. Never modify test files.
4. Check: run your snippet again, then run_tests() once (it is slow).
5. Submit: final_answer(get_patch()).

Rules:
- Exactly one ```python block per answer, then stop.
- Use print() to see results; keep outputs short (slice long strings).
- Do not look for the solution online or in the git history.
- Your code block runs in a restricted sandbox: it can only call the
  functions below, not import the project. To run the project's code, use
  run_command, e.g. run_command("python -c 'from sympy import S; print(S(1)
  + 1)'")
  The `python` there is already the project's environment.
- Never write the result of your code yourself: it is given back to you
  as the Observation.

"""


def on_sigterm(signum: int, frame: object) -> None:
    """
    Turn SIGTERM into SystemExit so that every finally block runs
    """
    raise SystemExit(143)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--task-file", default=None, required=True,
        help="path to the task file"
    )
    parser.add_argument(
        "--output", default=None, required=True,
        help="path to the output file"
    )
    parser.add_argument(
        "--model-name", default=DEFAULT_MODEL,
        help="name of the model"
    )
    parser.add_argument(
        "--provider-url", default=DEFAULT_PROVIDER_URL,
        help="provider url for the api key"
    )
    parser.add_argument(
        "--max-iterations", default=MAX_ITERATIONS, type=int,
        help="max_iterations for the llm"
    )
    parser.add_argument(
        "--no-fallback", action="store_true",
        help="benchmark mode: measure only the given model, no fallback"
    )

    return parser.parse_args()


def build_task_prompt(task: SWEBenchTaskInput) -> str:
    """
    Task given to the LLM: the issue, and the hints when there are some
    """
    prompt = (f"Fix this issue in the repository at /testbed: "
              f"\n\n{task.problem_statement}")
    if task.hints_text.strip():
        prompt += f"\n\nHints from the discussion:\n{task.hints_text}"
    return prompt


def write_solution(path: str, task: SWEBenchTaskInput, run: AgentRun,
                   patch: str, system_prompt: str, start: float) -> None:
    """
    Write solution.json: called in every case, even after a crash
    """
    # get_patch returns a message, not a patch, when nothing changed
    if not patch.startswith("diff"):
        patch = ""
    solution = SolutionOutput(
        task_id=task.instance_id,
        benchmark="swebench",
        success=run.answer is not None,
        solution=patch,
        iterations=len(run.steps),
        total_requests=sum(s.retries + 1 for s in run.steps),
        total_input_tokens=sum(s.input_tokens for s in run.steps),
        total_output_tokens=sum(s.output_tokens for s in run.steps),
        total_time_seconds=time.monotonic() - start,
        steps=run.steps,
        system_prompt=system_prompt,
        error=run.error
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(solution.model_dump_json(indent=2))


def main() -> None:
    start = time.monotonic()
    deadline = start + DEADLINE_SECONDS
    signal.signal(signal.SIGTERM, on_sigterm)
    load_dotenv()
    args = parse_args()
    task = SWEBenchTaskInput.model_validate_json(Path(
        args.task_file).read_text())

    run = AgentRun(None, [], "agent did not start")
    system_prompt = ""
    patch = ""
    container = bridge = sandbox = None
    try:
        # 1. the container, with the evaluation script inside
        container = Container(task.docker_image,
                              os.environ.get("DOCKER_CMD", "docker"))
        container.start()
        container.write_file(EVAL_PATH, task.eval_script)

        # 2. the tool server, pointed at this container
        env = {"SWEBENCH_CONTAINER": container.name, "EVAL_SCRIPT": EVAL_PATH}
        env.update({k: v for k, v in os.environ.items()
                    if k in DOCKER_ENV_VARS
                    or k.startswith(DOCKER_ENV_PREFIXES)})
        bridge = McpBridge(StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "mcp_tools_swebench.py")], env=env))

        # 3. sandbox, prompts, client and loop: like MBPP
        config_sandbox = load_config(None)
        sandbox = Sandbox(config_sandbox, bridge)
        manual = build_manual(bridge.list_tools(), config_sandbox)
        system_prompt = SYSTEM_RULES + "\n" + manual
        llm_config = LLMConfig.from_file(ROOT / "config/llm.json")
        if args.no_fallback:
            llm_config.fallbacks = []
        client = LLMClient(llm_config, args.provider_url, args.model_name)
        run = run_agent(
            client, sandbox, system_prompt, build_task_prompt(task),
            args.max_iterations, deadline,
            MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS)

        # 4. the patch, taken from the container itself
        patch = bridge.call_tool("get_patch", {})
    except Exception as e:
        run.error = f"{type(e).__name__}: {e}"
    finally:
        # close in reverse order of creation, then ALWAYS write the output
        if sandbox:
            sandbox.close()
        if bridge:
            bridge.close()
        if container:
            container.stop()
        write_solution(args.output, task, run, patch, system_prompt, start)


if __name__ == "__main__":
    main()
