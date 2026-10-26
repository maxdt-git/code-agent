from mcp.server.fastmcp import FastMCP
import subprocess
import os
import shlex


COMMAND_TIMEOUT = 60
TESTS_TIMEOUT = 600
MAX_OUTPUT_CHARS = 10000
MAX_MATCHES = 100
TESTBED = os.environ.get("TESTBED_PATH", "/testbed")
# set by agent when repo in container
CONTAINER = os.environ.get("SWEBENCH_CONTAINER")
# path of eval script
EVAL_SCRIPT = os.environ.get("EVAL_SCRIPT")
DOCKER = os.environ.get("DOCKER_CMD", "docker")
CONTAINER_SETUP = os.environ.get(
    "CONTAINER_SETUP",
    "source /opt/miniconda3/bin/activate testbed 2>/dev/null; "
)

mcp = FastMCP("swebench-tool")


def to_local(path: str) -> str:
    """
    /testbed/... -> real folder when no running container
    """
    if CONTAINER is None and (
            path == "/testbed" or path.startswith("/testbed/")):
        return TESTBED + path[len("/testbed"):]
    return path


def to_agent(path: str) -> str:
    """
    Inverse of to_local: show a local path as /testbed/... to the agent
    """
    if path == TESTBED or path.startswith(TESTBED + "/"):
        return "/testbed" + path[len(TESTBED):]
    return path


def truncate(text: str, keep: str = "end") -> str:
    """
    Cut a long output to MAX_OUTPUT_CHARS, keeping its start or its end
    """
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    if keep == "start":
        return (text[:MAX_OUTPUT_CHARS] +
                f"\n[output truncated: showing first {MAX_OUTPUT_CHARS} "
                f"of {len(text)} characters]")
    return (f"[output truncated: showing last {MAX_OUTPUT_CHARS} of "
            f"{len(text)} characters]\n" + text[-MAX_OUTPUT_CHARS:])


def shell(
        command: str,
        workdir: str = "/testbed/",
        timeout: int = COMMAND_TIMEOUT,
        stdin: str | None = None
) -> tuple[int, str, str]:
    """
    Run a bash command, in the container if there is one, else locally.
    Returns (exit code, stdout, stderr)
    """
    if CONTAINER is not None:
        # -w choose start folder -> workdir
        # -i keep open when need to write
        argv = (DOCKER, "exec", "-i", "-w", workdir, CONTAINER,
                "bash", "-c", CONTAINER_SETUP + command)
        cwd = None
    else:
        argv = ["bash", "-c", command]
        cwd = to_local(workdir)

    try:
        done = subprocess.run(
            argv, cwd=cwd, input=stdin, capture_output=True,
            text=True, timeout=timeout, errors="replace"
        )

    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout} seconds"
    except OSError as e:
        return 1, "", str(e)

    return done.returncode, done.stdout, done.stderr


@mcp.tool()
def run_command(
    command: str,
    workdir: str = "/testbed"
) -> str:
    """
    Run a shell command in workdir, return stdout, stderr and exit code
    """
    code, out, err = shell(command, workdir)
    return truncate(
        f"exit code: {code}\n"
        f"--- stdout ---\n{out or '(empty)'}\n"
        f"--- stderr ---\n{err or '(empty)'}"
    )


@mcp.tool()
def list_files(
    directory: str,
    pattern: str
) -> str:
    """
    List files in a directory matching a given pattern
    """
    dir = "." if directory.rstrip("/") == "/testbed" else directory
    code, out, err = shell(
        f"find {shlex.quote(dir)} -type f -name {shlex.quote(pattern)} "
        "-not -path '*/.git/*'"
    )
    if code != 0:
        return f"Cannot list {directory}: {err.strip()}"

    files = sorted(
        "/testbed/" + f.removeprefix("./") if f.startswith("./") else f
        for f in out.splitlines()
    )

    if not files:
        return f"No file matches {pattern} in {directory}"

    return truncate("\n".join(files), keep="start")


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
    target = filepath if CONTAINER else to_local(filepath)
    code, out, err = shell(f"cat {shlex.quote(target)}")
    if code != 0:
        return f"Cannot read {filepath}: {err.strip()}"

    data = out.splitlines()
    end = len(data) if end_line is None else end_line
    rows = [f"{n}: {line}" for n, line in enumerate(
        data[start_line - 1:end], start=start_line
    )]
    if not rows:
        return f"{filepath} has only {len(data)} rows"

    return truncate("\n".join(rows), keep="start")


@mcp.tool()
def get_patch() -> str:
    """
    Retrieve the unified git diff of all changes made to the repository
    """
    code, out, err = shell("git -c core.fileMode=false diff")
    if code != 0:
        return err

    if not out:
        return "No changes yet"

    return out


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*.py") -> str:
    """
    Perform a grep-like search of file_pattern in the codebase, file_pattern
    is a path or or global name "*.py"
    """
    if "/" in file_pattern:
        # a path like sympy/core/add.py: search in it, not by file name
        where = shlex.quote(file_pattern.removeprefix("/testbed/"))
        include = ""
    else:
        where = "."
        include = f"--include={shlex.quote(file_pattern)}"

    command = (f"grep -rnHE {include} --exclude-dir=.git "
               f"-- {shlex.quote(pattern)} {where}")

    code, out, err = shell(command)
    if code == 1:
        return f"No match for {pattern!r} in {file_pattern} files"
    if code != 0:
        return f"search_code failed: {err.strip()}"

    results: list[str] = []
    for line in out.splitlines():
        path, number, content = line.split(":", 2)
        results.append(f"/testbed/{path.removeprefix('./')}:{number} {content}")

    total = len(results)
    results = results[:MAX_MATCHES]
    if total > MAX_MATCHES:
        results.append(f"[{total - MAX_MATCHES} more matches not shown, "
                       "use a more precise pattern]")

    return "\n".join(results)


def grep_word(name: str) -> list[tuple[str, str, str]]:
    """
    Lines of .py files where name appears as a whole word,
    as (path, line number, content)
    """
    code, out, _ = shell(f"grep -rnwF --include='*.py' --exclude-dir=.git "
                         f"-- {shlex.quote(name)} .")
    if code != 0:
        return []
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        path, number, content = line.split(":", 2)
        rows.append(("/testbed/" + path.removeprefix("./"), number, content))
    return rows


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """
    Find where a function or class is defined, same format as search_code
    """
    starts = (f"def {name}(", f"async def {name}(",
              f"class {name}(", f"class {name}:")
    rows = [row for row in grep_word(name)
            if row[2].strip().startswith(starts)]
    if not rows:
        return f"No definition of {name!r} found"
    return "\n".join(f"{path}:{number} {content}"
                     for path, number, content in rows)


@mcp.tool()
def find_references(name: str, filepath: str, line: int) -> str:
    """
    Find every usage of a symbol, same format as search_code
    """
    rows = grep_word(name)
    if not rows:
        return f"No reference to {name!r} found"
    shown = [f"{path}:{number} {content}"
             for path, number, content in rows[:MAX_MATCHES]]
    if len(rows) > MAX_MATCHES:
        shown.append(f"[{len(rows) - MAX_MATCHES} more references not shown]")
    return "\n".join(shown)


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """
    Replace the exact text old_str by new_str in a file (once)
    """
    target = filepath if CONTAINER else to_local(filepath)
    code, out, err = shell(f"cat {shlex.quote(target)}")
    if code != 0:
        return f"Cannot read {filepath}: {err.strip()}"
    count = out.count(old_str)
    if count == 0:
        return (
            f"{old_str} not found, (must be exactly the same, "
            "use read_file)")
    if count > 1:
        return f"Found {count} times, try to make it unique"

    new_content = out.replace(old_str, new_str, 1)
    # write in the file
    code, _, err = shell(f"cat > {shlex.quote(target)}", stdin=new_content)
    if code != 0:
        return f"Cannot write {filepath}: {err.strip()}"


    if target.endswith(".py"):
        returncode, _, err = shell(f"python -m py_compile {shlex.quote(target)}")
        if returncode != 0:
            shell(f"cat > {shlex.quote(target)}", stdin=out)
            return (f"Edit rejected: it breaks the syntax of {filepath}, "
                    f"the file was restored.\n{err.strip()}")
    return f"Edited {filepath}: 1 occurence replaced"


@mcp.tool()
def run_tests() -> str:
    """
    Run the evaluation script of the task and return its output
    """
    if EVAL_SCRIPT is None:
        return "Noe evaluation script provided"
    code, out, err = shell(f"bash {shlex.quote(EVAL_SCRIPT)}", timeout=TESTS_TIMEOUT)
    return f"exit code: {code}\n{truncate(out + err)}"


if __name__ == "__main__":
    mcp.run()
    # print(list_files("~/Documents/agent_smith/src/agent_smith/", "*.py"))
    # print(read_file("/home/mde-nas/Documents/agent_smith/src/agent_smith/agent/loop.py", 1, None))
