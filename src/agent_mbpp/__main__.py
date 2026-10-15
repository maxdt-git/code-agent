import argparse
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from mcp import StdioServerParameters
from agent_smith.agent.loop import AgentRun, run_agent
from agent_smith.llm.client import LLMClient
from agent_smith.llm.config import LLMConfig
from agent_smith.models import MBPPTaskInput, SolutionOutput
from agent_smith.sandbox.manual import build_manual
from agent_smith.sandbox.mcp_bridge import McpBridge
from agent_smith.sandbox.sandbox import Sandbox
from agent_smith.sandbox.cli import load_config


DEADLINE_SECONDS = 105          # limit 120 with mbpp
DEFAULT_MODEL = "qwen/qwen3.8-27b"
DEFAULT_PROVIDER_URL = "https://api.groq.com/openai/v1"
MAX_INPUT_TOKENS = 6000
MAX_OUTPUT_TOKENS = 1500


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
        "--max-iterations", default=8, type=int,
        help="max_iterations for the llm"
    )

    return parser.parse_args()


SYSTEM_RULES = """You are an expert Python programmer. You solve one task by \
writing Python code that runs in a sandbox.

Answer format, every turn:
Thought: one short sentence.
```python
<your code>
```<end_code>

Rules:
- Exactly one ```python block per answer, then stop. Never write the \
Observation yourself.
- Put the whole solution in a string named `code`: the function and the \
imports it needs.
- The variable `tests` already holds the test assertions: never rewrite them.
- Use exactly the function name and parameters given in the task.
- Write a general solution: hidden tests are run too, never hard-code \
expected values.
- If the tests fail, read the output, fix the function and test again.

Example:
Thought: I write the function, test it and submit if it passes.
```python
import json
code = '''
def add(a, b):
    return a + b
'''
result = json.loads(run_tests(code, tests))
print(result)
if result["success"]:
    final_answer(code)
```<end_code>
"""


def build_task_prompt(task: MBPPTaskInput) -> str:
    """
    Task given to the LLM: statement, exact signature and public tests
    """
    return (
        f"Task: {task.task_definition}\n"
        f"Function signature (use exactly this): {task.function_definition}\n"
        "Public tests (already stored in `tests`):\n"
        + "\n".join(task.test_list)
    )


def main() -> None:
    start = time.monotonic()
    deadline = start + DEADLINE_SECONDS
    load_dotenv()
    args = parse_args()
    task = MBPPTaskInput.model_validate_json(Path(args.task_file).read_text())

    run = AgentRun(None, [], "agent did not start")
    system_prompt = ""
    bridge = sandbox = None
    config_sandbox = load_config(None)
    try:
        bridge = McpBridge(StdioServerParameters(command=sys.executable,
                           args=["mcp_tools_mbpp.py"]))
        sandbox = Sandbox(config_sandbox, bridge)
        tools = bridge.list_tools()
        manual = build_manual(tools, config_sandbox)
        sandbox.execute(f"tests = {task.test_imports + task.test_list!r}")
        system_prompt = SYSTEM_RULES + "\n" + manual
        task_prompt = build_task_prompt(task)
        client = LLMClient(
            LLMConfig.from_file("config/llm.json"),
            args.provider_url, args.model_name
        )
        run = run_agent(
            client, sandbox, system_prompt, task_prompt, args.max_iterations,
            deadline, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS
        )
    except Exception as e:
        run.error = f"{type(e).__name__}: {e}"
    finally:
        if sandbox:
            sandbox.close()
        if bridge:
            bridge.close()

    solution = SolutionOutput(
        task_id=str(task.task_id),
        benchmark="mbpp",
        success=run.answer is not None,
        solution=run.answer or "",
        iterations=len(run.steps),
        total_requests=sum(s.retries + 1 for s in run.steps),
        total_input_tokens=sum(s.input_tokens for s in run.steps),
        total_output_tokens=sum(s.output_tokens for s in run.steps),
        total_time_seconds=time.monotonic() - start,
        steps=run.steps,
        system_prompt=system_prompt,
        error=run.error
    )

    Path(args.output).write_text(solution.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
