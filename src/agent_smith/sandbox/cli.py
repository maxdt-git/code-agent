from agent_smith.models import SandboxConfig
from agent_smith.sandbox.sandbox import Sandbox
from agent_smith.sandbox.executor import ExecutionResult
import argparse
from pathlib import Path
import sys
from mcp import StdioServerParameters
from agent_smith.sandbox.mcp_bridge import McpBridge
import shlex
import ast


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
    # refuse both options together
    group = parser.add_mutually_exclusive_group()
    # command that starts an MCP server, talking on stdin/stdout
    group.add_argument(
        "--mcp-stdio", default=None,
        help="command that start an MCP server over stdio"
    )
    # URL of an MCP server already running (HTTP)
    group.add_argument(
        "--mcp-server", default=None,
        help="URL of a streamable HTTP MCP server"
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


def split_statements(source: str) -> list[str]:
    """
    Cut a script into multiple statements
    """
    # analyse text
    try:
        tree = ast.parse(source)
    # if we cant cut it or just syntaxerror
    except SyntaxError:
        return [source]

    lines = source.splitlines()
    statements: list[str] = []
    # last treat line
    done: int = 0

    for node in tree.body:
        # in case there is a decorator (func or class)
        first = min(
            [node.lineno] +
            [d.lineno for d in getattr(node, "decorator_list", [])])
        if first <= done:
            continue
        done = node.end_lineno or first
        # append all the block we cut
        statements.append("\n".join(lines[first - 1:done]))
    return statements


def connect(args: argparse.Namespace) -> McpBridge | None:
    """
    Connect to the mcp server given on the command line if there is one
    """
    if args.mcp_stdio is not None:
        # split like a shell : 'python x.py' -> ['python', 'x.py']
        # shlex to analyse and manipulate python str like a shell
        # -> respect guill
        parts = shlex.split(args.mcp_stdio)
        if not parts:
            raise ValueError("--mcp-stdio needs a command")
        return McpBridge(
            StdioServerParameters(command=parts[0], args=parts[1:])
        )
    if args.mcp_server is not None:
        return McpBridge(args.mcp_server)
    return None


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

    try:
        bridge = connect(args)
        # connection failed or empty command
    except (RuntimeError, ValueError) as e:
        print(f"cannot start mcp server: {e}")
        sys.exit(1)

    if bridge is not None:
        names = ", ".join(tool.name for tool in bridge.list_tools())
        print(f"MCP tools: {names}")

    # starts the child process
    sandbox = Sandbox(config, bridge)
    try:
        if not sys.stdin.isatty():
            for statement in split_statements(sys.stdin.read()):
                if statement.strip() == "exit":
                    break
                show(sandbox.execute(statement))
            return
        while True:
            entry = read_entry()
            # Ctrl+D -> newline so the shell prompt starts clean
            if entry is None:
                print()
                break
            # "exit" is a command of the REPL, not python code
            if entry.strip() == "exit":
                break
            if entry.strip() == "manual":
                print(sandbox.manual)
                continue

            # empty line -> just show the prompt again
            if not entry.strip():
                continue
            show(sandbox.execute(entry))

    # Ctrl+C -> leave without a traceback
    except KeyboardInterrupt:
        print()
    # always runs, even on error -> the child is never left behind
    finally:
        # first close sandbox or it can call non existent tools
        sandbox.close()
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
