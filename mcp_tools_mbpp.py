from mcp.server.mcpserver import MCPServer
import json
import subprocess
import sys


TEST_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 1000


mcp = MCPServer("mbpp-tools")


def truncate(text: str) -> str:
    """
    Keep the end of the text when it is longer than MAX_OUTPUT_CHARS
    """
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return (
        f"[output truncated: showing last {MAX_OUTPUT_CHARS} of "
        f"{len(text)} characters]\n" + text[-MAX_OUTPUT_CHARS:]
    )


# save the function in an intern mcp register (dict{name: the function})
@mcp.tool()
def run_tests(code: str, test_list: list[str]) -> str:
    """
    Run a candidate solution against test assertion

    Returns a JSON string with "success" (true when assertion passed")
    and "output" (stdout, stderr ans error messages)
    """
    script = code + "\n" + "\n".join(test_list)

    # return args
    # return code
    # None if not captured -> stdout, stderr
    # sys.executable -> command run like its python code -c
    # capture to get it under text if True instead of bytes
    try:
        complete = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "output": (
                f"Tests timed out after {TEST_TIMEOUT_SECONDS} seconds. "
                "The code probably contains an infinite loop.")
        })

    output = complete.stdout + complete.stderr

    return json.dumps({
        "success": complete.returncode == 0,
        "output": truncate(output)
    })


if __name__ == "__main__":
    mcp.run()
