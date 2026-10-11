from agent_smith.models import SandboxConfig
from agent_smith.sandbox.sandbox import Sandbox
from agent_smith.sandbox.executor import ExecutionResult
import argparse
from pathlib import Path
import sys


# __file__ -> src/agent_smith/sandbox/cli.py
# parents[3] -> the root of the project, 3 folders above
# works whatever the directory the command is launched from
DEFAULT_CONFIG = str(
    Path(__file__).resolve().parents[3]/"config/sandbox.json"
)


def parse_args() -> argparse.Namespace:
    """
    Read the command line, optionnal config file and MCP options
    """
    parser = argparse.ArgumentParser(
        description="Interactive sandbox"
    )
    # nargs="?" -> positional but optional (0 or 1 value)
    # uv run sandbox            -> config is None
    # uv run sandbox file.json  -> config is "file.json"
    parser.add_argument(
        "config", nargs="?", default=None,
        help="path to a sandbox json config file"
    )
    # command that starts an MCP server, talking on stdin/stdout
    parser.add_argument(
        "--mcp-stdio", default=None,
    )
    # URL of an MCP server already running (HTTP)
    parser.add_argument(
        "--mcp-server", default=None,
    )

    return parser.parse_args()


def load_config(path: str | None) -> SandboxConfig:
    """
    Load sandbox config or default if nothing is provided
    """
    if path is None:
        path = DEFAULT_CONFIG
    # read_text -> OSError if the file is missing
    # model_validate_json -> ValueError if the json is invalid
    # both are caught in main
    return SandboxConfig.model_validate_json(Path(path).read_text())


def show(result: ExecutionResult) -> None:
    """
    Print one execution
    """
    # end="" -> the output already has its own newlines
    if result.output:
        print(result.output, end="")
    # add a newline only if the error does not end with one
    if result.error is not None:
        print(result.error, end="" if result.error.endswith("\n") else "\n")
    if result.final_answer is not None:
        print(f"[final answer] >>> {result.final_answer}")


def read_entry() -> str | None:
    """
    Read one entry, a single line or a block
    """
    # EOFError -> Ctrl+D or end of a piped input
    # None tells main to leave the loop
    try:
        line = input(">>> ")
    except EOFError:
        return None
    # no ":" at the end -> a complete single line
    if not line.rstrip().endswith(":"):
        return line

    # ":" at the end -> a block (def, for, if...)
    # keep reading until an empty line, like the python prompt
    lines = [line]
    while True:
        try:
            more = input("... ")
        except EOFError:
            break
        if not more.strip():
            break

        lines.append(more)

    return "\n".join(lines)


def main() -> None:
    """
    Interactive sandbox, read code, run it and print the result
    """
    args = parse_args()
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as e:
        print(f"cannot load sandbox config: {e}")
        sys.exit(1)

    # starts the child process
    sandbox = Sandbox(config)
    try:
        while True:
            entry = read_entry()
            # Ctrl+D -> newline so the shell prompt starts clean
            if entry is None:
                print()
                break
            # "exit" is a command of the REPL, not python code
            if entry.strip() == "exit":
                break
            # empty line -> just show the prompt again
            if not entry.strip():
                continue
            show(sandbox.execute(entry))

    # Ctrl+C -> leave without a traceback
    except KeyboardInterrupt:
        print()
    # always runs, even on error -> the child is never left behind
    finally:
        sandbox.close()
