from mcp.server.fastmcp import FastMCP
import subprocess
import os
import shlex


COMMAND_TIMEOUT = 60
TESTBED = os.environ.get("TESTBED_PATH", "/testbed")

mcp = FastMCP("swebench-tool")


def to_local(path: str) -> str:
    """
    Map an agent path (/testbed/...) to the real folder of TESTBED_PATH
    """
    if path == "/testbed" or path.startswith("/testbed/"):
        return TESTBED + path[len("/testbed"):]
    return path


@mcp.tool()
def run_command(
    command: str,
    workdir: str = "/testbed"
) -> str:
    """
    Run a shell command in workdir, return stdout, stderr and exit code
    """
    try:
        complete = subprocess.run(
            ["bash", "-c", command],
            cwd=to_local(workdir),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT
        )

    except subprocess.TimeoutExpired:
        return f"Command timed out after {COMMAND_TIMEOUT} seconds: {command}"
    except OSError as e:
        return f"Cannot run the command in {workdir}: {e}"

    return (
        f"exit code: {complete.returncode}\n"
        f"--- stdout ---\n{complete.stdout or '(empty)'}\n"
        f"--- stderr ---\n{complete.stderr or '(empty)'}"
    )


def to_agent(path: str) -> str:
    """
    Inverse of to_local: show a local path as /testbed/... to the agent
    """
    if path == TESTBED or path.startswith(TESTBED + "/"):
        return "/testbed" + path[len(TESTBED):]
    return path


@mcp.tool()
def list_files(
    directory: str,
    pattern: str
) -> str:
    """
    List files in a directory matching a given pattern
    """
    local = to_local(directory)
    command = (f"find {shlex.quote(local)} -type f -name"
               f"{shlex.quote(pattern)} -not -path '*/.git/*'")
    try:
        complete = subprocess.run(
            ["bash", "-c", command],
            capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT
        )

    except subprocess.TimeoutExpired:
        return f"Command timed out after {COMMAND_TIMEOUT} seconds: {command}"
    if complete.returncode != 0:
        return f"Cannot list {directory}: {complete.stdout.splitlines()}"
    files = sorted(to_agent(line) for line in complete.stdout.splitlines())
    if not files:
        return f"No file matches {pattern!r} in {directory}"
    return "\n".join(files)


@mcp.tool()
def read_file(
    filepath: str,
    start_line: int = 1,
    end_line: int | None = None
) -> str:
    """
    Read the content of a file with line numbers, output format
    is similar to cat -n
    """
    local = to_local(filepath)
    try:
        # replace illisble octet
        with open(local, encoding="utf-8", errors="replace") as f:
            data = f.read().splitlines()
    except FileNotFoundError:
        return f"Cannot find a file with the path: {filepath}"
    except OSError as e:
        return f"Cannot open the file {filepath}, error: {e}"

    if end_line is None:
        end_line = len(data)
    if start_line > end_line:
        return f"{filepath} has only {len(data)} lines"

    selected = data[start_line - 1:end_line]
    result = [f"{number}: {line}"
              for number, line in enumerate(selected, start=start_line)]

    if not result:
        return f"{filepath} has only {len(data)} lines"

    return "\n".join(result)



if __name__ == "__main__":
    mcp.run()
    # print(list_files("~/Documents/agent_smith/src/agent_smith/", "*.py"))
    # print(read_file("/home/mde-nas/Documents/agent_smith/src/agent_smith/agent/loop.py", 1, None))
