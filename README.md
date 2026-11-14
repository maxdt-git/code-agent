# Code Agent

**Stack:** Python · Docker/Podman sandbox · MCP · LLM APIs (Groq, Gemini, OpenRouter) · uv

**Highlights**
- Agent loop, sandbox, MCP client and LLM client written from scratch — no agent framework
- **SWE-bench Verified: 3/3** on the evaluated tasks (6/6 on the full exam pool) · **MBPP: 19/20**
- Benchmarked 5 models across 3 providers; an output-trimming fix cut input tokens by 33 % at equal score

## Description

This is a code agent built from scratch: an LLM solves coding tasks
by writing Python code that runs in a sandbox, reading the result, and
trying again until it submits an answer (Thought → Code → Observation).

It is applied to two benchmarks:

- **MBPP**: write a Python function that passes given tests.
- **SWE-bench Verified**: fix a real bug in a real repository (sympy,
  django, xarray…) inside its Docker container, and return a git patch.

The agent loop, the sandbox, the MCP client and the LLM client are our own
code: no agent framework is used.

## Instructions

Requirements: Python 3.10, [uv](https://docs.astral.sh/uv/), Docker or
Podman, and free-tier API keys.

```bash
make install                 # Python, dependencies, moulinette
cp .env.example .env         # then add your keys (GROQ_API_KEY, GEMINI_API_KEY, ...)
```

Several keys per provider are accepted (`GROQ_API_KEY_1`, `GROQ_API_KEY_2`…).
They rotate on rate limits.

Run the agents:

```bash
uv run python -m agent_mbpp --task-file task.json --output solution.json \
    [--model-name qwen/qwen3.8-27b --provider-url https://api.groq.com/openai/v1]
uv run python -m agent_swebench --task-file task.json --output solution.json
```

Sandbox REPL:

```bash
uv run sandbox [config.json]
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py"
uv run sandbox --mcp-server http://localhost:8000/mcp
```

Exams: `make exam-sandbox`, `make exam-mbpp`, `make exam-swebench`,
`make exam-anticheat`.

> **Rootless Podman (42 computers):** `make exam-*` starts
> `podman.socket` and runs SWE-bench under `podman unshare`. When you run
> `./exams/exam_swebench.sh` by hand, do the same:
> `systemctl --user start podman.socket`, then
> `podman unshare ./exams/exam_swebench.sh ...`.

Defaults: `qwen/qwen3.8-27b` on Groq for both agents. Configuration is in
`config/llm.json` (providers, retries, backoff) and `config/sandbox.json`
(imports, directories, time and memory limits).

## System architecture

```
agent_mbpp / agent_swebench     CLI: load the task, build the prompt, write solution.json
        │
   agent/loop.py                Thought → Code → Observation loop, budgets, metrics
   ├── llm/client.py            LLM calls: key rotation, retries, fallback, timing
   ├── agent/extract.py         code extraction from the model's answer
   └── sandbox/sandbox.py       runs the code in a child process
            ├── worker.py + executor.py + guards.py   restricted execution
            └── mcp_bridge.py   MCP client (stdio or HTTP)
                     │
        mcp_tools_mbpp.py / mcp_tools_swebench.py     our MCP servers
                     │
              docker exec into the task container (SWE-bench)
```

| Package | Role |
|---|---|
| `src/agent_smith/llm/` | OpenAI-compatible backend, `KeyPool` (several keys per provider), typed errors (rate limit, quota, model unavailable) |
| `src/agent_smith/agent/` | agent loop and code extraction |
| `src/agent_smith/sandbox/` | sandbox, security guards, MCP bridge, manual, REPL |
| `src/agent_smith/swebench/` | Docker container lifecycle |
| `src/agent_smith/models.py` | Pydantic models: `StepMetrics`, `SolutionOutput`, `SandboxConfig`, task inputs |

## Agent loop

1. The system prompt contains the rules, the answer format, a worked
   example, and the **sandbox manual**, generated from the MCP tool schemas.
2. Each step, the LLM answers with a `Thought:` and one ```` ```python ````
   block. Generation stops at `<end_code>`, so the model cannot invent the
   observation.
3. The extractor takes the code. It also accepts XML, JSON/Hermes and
   ReAct tool calls and converts them to Python calls, with a note to the
   model saying what it did.
4. The sandbox runs the code. Its printed output, errors, and notes
   (timeout, truncation, no code found) are sent back as the next
   `Observation:`.
5. The loop ends when the code calls `final_answer(...)`, or when the
   iteration, token or time budget would be exceeded. The budget is checked
   **before** each LLM call.
6. Every step is logged in `solution.json`: tokens, latency, retries,
   endpoint, model, raw LLM output, sandbox input and sandbox output.

For SWE-bench, the patch is always read from the container at the end
(`git -c core.fileMode=false diff`), so work done before an LLM failure is
not lost.

## Sandbox design

The code runs in a **separate process** (`multiprocessing`, spawn), so it
can be killed at any time. It is checked in three layers, using only the
Python standard library:

| Constraint | How |
|---|---|
| Imports | allowlist from the config (`module.*` allows submodules). The code receives a filtered copy of the module, so `math.os` or `collections.sys` are not reachable. |
| Files | `open` is replaced. The path is resolved (`realpath`, which removes `..` and symlinks) before it is compared to `allowed_directories`. |
| Builtins | `eval`, `exec`, `compile`, `globals`, `vars`, `input`… are removed. Dunder and frame attributes are blocked, both by an AST check before execution and by `getattr`. |
| Network | `socket` is not allowed, and `socket.socket` is replaced by a class that refuses to be created, so even an allowed module cannot connect. |
| Timeout | the parent waits on a pipe with a deadline, then kills the child and starts a new one. Output already printed is kept. Time spent in MCP tools does not count. |
| Memory | `RLIMIT_AS` is set in the child. If the child dies, the LLM is told, and a new child is started. |

The child's environment is emptied, so API keys cannot be read from
sandboxed code. `KeyboardInterrupt` and `SystemExit` are propagated to the
agent loop. `final_answer` is injected by the sandbox itself: it is not an
MCP tool.

MCP tools are discovered at start-up (`list_tools`) and exposed as Python
functions. A call goes from the child to the parent through the pipe, then
from the parent to the MCP server. The bridge can also list the server's
resources and prompts.

## Tool implementation

**`mcp_tools_mbpp.py`**: `run_tests(code, test_list)` runs the code and the
assertions in a subprocess with a 10 s timeout. It returns
`{"success": bool, "output": str}`.

**`mcp_tools_swebench.py`** (FastMCP, stdio): every tool runs
`docker exec` in the task container. Without a container, it runs locally
on `TESTBED_PATH`.

| Tool | Implementation |
|---|---|
| `read_file` | `cat`, then numbered lines `n: content` |
| `edit_file` | exact, unique replacement. A `.py` file is checked with `py_compile`, and the edit is **reverted** with an explicit message if it breaks the syntax. |
| `list_files` | `find -name pattern`, without `.git` |
| `search_code` | `grep -rnE`, output `/testbed/path:line content`, 100 matches at most |
| `search_function_or_class_definition_in_code` | whole-word grep filtered on `def name(` / `class name` |
| `find_references` | whole-word grep on `.py` files |
| `run_tests` | runs the task's eval script and returns only the part between `>>>>> Start/End Test Output`, without the `set -x` trace |
| `get_patch` | `git -c core.fileMode=false diff` |
| `run_command` | shell command in the project's conda environment, returns exit code, stdout and stderr |

Long outputs are truncated with an explicit
`[output truncated: showing … of N characters]` line.

**Container lifecycle:** the container runs `cat` on a pipe held by the
agent, with `--rm`. If the agent exits for any reason, even `kill -9`, the
pipe closes, the container stops and is removed. `SIGTERM` is turned into
`SystemExit`, so cleanup and `solution.json` are always written.

## Benchmark results and analysis

Full report: [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md). Backing data is in
`benchmark/`.

5 models, 3 providers (Groq, Gemini, OpenRouter), on the same 3 SWE-bench
tasks (sympy-13480, xarray-4629, sympy-14711):

| Model | Provider | Score | Input tokens (3 tasks) |
|---|---|---|---|
| `qwen/qwen3.8-27b` | Groq | 3/3 (6/6 on the whole exam pool) | 99,846 |
| `gemini-3.5-flash-lite` | Gemini | 3/3 | 219,202 |
| `gemini-3.6-flash` | Gemini | 2/3 | 230,586 |
| `openai/gpt-oss-120b` | Groq | 1/3 | 30,640 |
| `cohere/north-mini-code:free` | OpenRouter | 0/3 | 131,138 |

- **Selected:** `qwen/qwen3.8-27b`. It has the best pass rate and the
  fewest input tokens of the models that pass, and answers in about 0.5 s
  per request. Its limit is Groq's free quota (200,000 tokens per day).
  `gemini-3.5-flash-lite` is the backup.
- **Failures come from formats and quotas, not from reasoning:**
  north-mini-code never uses the expected code format, gpt-oss calls its
  own built-in tools (rejected by Groq), and gemini-3.6-flash runs out of
  daily requests.
- **Ablation:** `run_tests` used to return the last 10,000 characters of
  output, which were only the `set -x` trace, so the model never saw its
  test results. Returning only the test section cut input tokens by 33 %,
  with the same 3/3.
- **MBPP:** `qwen/qwen3.8-27b`, 19/20 with about 1,400 input tokens per
  task (limit 6,000).

## Resources

- [Model Context Protocol](https://modelcontextprotocol.io/) and its
  [Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [SWE-bench Verified](https://www.swebench.com/)
- Python documentation: `ast`, `multiprocessing`, `resource`, `builtins`
- [OpenAI Python SDK](https://github.com/openai/openai-python) (used with
  OpenAI-compatible endpoints), Groq, Gemini and OpenRouter API docs

### Use of AI

AI assistants (Claude) were used for:

- **Explanations:** sandbox escape techniques to block, MCP transports,
  rate-limit handling.
- **Debugging the environment:** making Docker work with rootless Podman
  on the 42 computers (socket, image names, `podman unshare`).
- **Review:** reviewing code and the benchmark report, and checking the
  numbers against the `solution.json` files.
- **Writing:** help with wording the documentation.

The architecture, the agent loop, the sandbox and the tools were designed
and written by me. Every AI suggestion was read, tested and understood
before being kept.
