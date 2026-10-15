from mcp.server.fastmcp import FastMCP
import subprocess
import os


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
            timeout=60
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


if __name__ == "__main__":
    mcp.run()
