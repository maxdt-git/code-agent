from agent_smith.models import SandboxConfig
from agent_smith.sandbox.sandbox import Sandbox
from agent_smith.sandbox.executor import ExecutionResult
import argparse
from pathlib import Path
import sys


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
    parser.add_argument(
        "config", nargs="?", default=None,
        help="path to a sandbox json config file"
    )
    parser.add_argument(
        "--mcp-stdio", default=None,
    )
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
    return SandboxConfig.model_validate_json(Path(path).read_text())


def show(result: ExecutionResult) -> None:
    """
    Print one execution
    """
    if result.output:
        print(result.output, end="")
    if result.error is not None:
        print(result.error, end="" if result.error.endswith("\n") else "\n")
    if result.final_answer is not None:
        print(f"[final answer] >>> {result.final_answer}")


def read_entry() -> str | None:
    """
    Read one entry, a single line or a block
    """
    try:
        line = input(">>> ")
    except EOFError:
        return None
    if not line.rstrip().endswith(":"):
        return line

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

    sandbox = Sandbox(config)
    try:
        while True:
            entry = read_entry()
            if entry is None:
                print()
                break
            if entry.strip() == "exit":
                break
            if not entry.strip():
                continue
            show(sandbox.execute(entry))

    except KeyboardInterrupt:
        print()
    finally:
        sandbox.close()
