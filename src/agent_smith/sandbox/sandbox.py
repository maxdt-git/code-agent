import multiprocessing
from agent_smith.models import SandboxConfig
from agent_smith.sandbox.worker import worker_main
from agent_smith.sandbox.executor import ExecutionResult
import time
from typing import Any
from agent_smith.sandbox.mcp_bridge import McpBridge
from agent_smith.sandbox.manual import build_manual


class Sandbox:
    """
    Run code in a child process
    """
    def __init__(
            self,
            config: SandboxConfig,
            bridge: McpBridge | None = None
    ) -> None:
        self._config = config
        self._bridge = bridge
        self._tools: dict[str, Any] = {}
        if bridge is not None:
            self._tools = {tool.name: tool for tool in bridge.list_tools()}
        self.manual = build_manual(list(self._tools.values()), self._config)
        self._start()

    def _start(self) -> None:
        """
        Create pipe and launch child process
        """
        # get_context("spawn") starts a new python
        ctx = multiprocessing.get_context("spawn")
        # ctx.Pipe() create pipe and returns 2 sides
        # first in self._conn
        # second is child_conn
        self._conn, child_conn = ctx.Pipe()
        # ctx.process(..)
        # target=worker_main -> function he will execute
        # args -> ...
        # daemon=True -> if process stop, kill child
        self._process = ctx.Process(
            target=worker_main,
            args=(child_conn, self._config, list(self._tools), self.manual),
            daemon=True
        )
        # .start() -> start child
        self._process.start()
        # child_conn.close() -> parent dont need child anymore
        # he gets a copy
        # parent couldnt detect child is dead
        child_conn.close()

    def execute(self, code: str) -> ExecutionResult:
        """
        Send the code to the child and wait for result
        """
        limit = self._config.max_execution_time_seconds
        # monotonic -> a clock that never goes back
        deadline = time.monotonic() + limit
        # pieces of output received while the code runs
        # only used if the code never sends its final result
        chunks: list[str] = []
        self._conn.send(code)

        while True:
            # time left before the timeout
            remaining = deadline - time.monotonic()
            # poll -> did a response arrived??
            # waits at most "remaining" seconds, False if nothing came
            # -> time is over, leave the loop and go to the timeout part
            if remaining <= 0 or not self._conn.poll(remaining):
                break

            # every message is a pair (kind, payload)
            # EOFError / OSError -> the pipe is closed: the child is dead
            try:
                kind, payload = self._conn.recv()
            except (EOFError, OSError):
                self._restart()
                return ExecutionResult(
                    output="".join(chunks),
                    error=(
                        f"The sandbox process died, probably because it "
                        f"exceed the memory limit {self._config.max_memory_mb}"
                        ".\nThe sandbox was restarted: all variables, "
                        "functions and import from previous steps are lost"
                    ),
                    final_answer=None,
                )
            # "call" -> the code call an mcp tool
            if kind == "call":
                started = time.monotonic()
                self._conn.send(self._call_tool(*payload))
                # tool time doesnt count in sandbox timeout
                deadline += time.monotonic() - started
                continue
            if kind == "raise":
                raise payload
            # "result" -> the code is finished, payload is the full result
            if kind == "result":
                result: ExecutionResult = payload
                return result
            # "output" -> a piece of printed text, keep it and wait again
            chunks.append(payload)

        # only reached on timeout: the child is still running the code
        # the only way to stop it is to kill it and start a new one
        self._restart()
        return ExecutionResult(
                output="".join(chunks),
                error=(
                    f"Execution timed out after {limit} seconds and "
                    "was killed\nThe sandbox was restarted: all variables,"
                    " functions and import from previous steps are lost"
                ),
                final_answer=None,
                timed_out=True

        )

    def close(self) -> None:
        """
        Close the pipe and child process
        """
        self._conn.close()
        # wait until child finish -> 1 sec
        self._process.join(timeout=1)
        # if block in while True we force kill
        if self._process.is_alive():
            self._process.kill()
            self._process.join()

    def _restart(self) -> None:
        """
        Kill child and start new one
        """
        # if child is blockd
        # stop force
        # wait for the process to end kill
        self._process.kill()
        self._process.join()
        # useless old pipe
        self._conn.close()
        # new child new pipe
        self._start()

    def _call_tool(
            self,
            name: str,
            args: tuple[Any, ...],
            kwargs: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Call an mcp tool for the child, never raising
        """
        try:
            assert self._bridge is not None
            schema = self._tools[name].inputSchema
            # parameter names in the order declared by the tool
            names = list(schema.get("properties", {}))
            # if there is to much args
            if len(args) > len(names):
                raise TypeError(
                    f"{name}() take at most {len(names)} arguments, "
                    f"got {len(args)}"
                )
            # positionnal arguments -> named arguments
            arguments = dict(zip(names, args))
            arguments.update(kwargs)
            return (True, self._bridge.call_tool(name, arguments))
        except Exception as e:
            return (False, f"tool {name} failed: {e}")


# if __name__ == "__main__":
#     sb = Sandbox(SandboxConfig(authorized_imports=["math"],
#                                max_execution_time_seconds=10,
#                                max_memory_mb=100))
#     print(sb.execute("x = 5"))
#     print(sb.execute("print(x)"))
#     print(sb.execute("while True: pass"))
#     print(sb.execute("import os"))
#     print(sb._process.is_alive())
#     sb.close()
#     print(sb._process.is_alive())
#     print("========= get in memory precedent discu")
#     print(sb.execute("print('etape ok')\nwhile True: pass"))
#     print("========= memory error")
#     print(sb.execute("x = 'a' * 10 ** 10"))
#     print(sb.execute("print('here')"))
#     sb.close()
#     print("======== socket")
#     sb = Sandbox(SandboxConfig(authorized_imports=["socket"],
#                                max_execution_time_seconds=10,
#                                max_memory_mb=100))
#     print(sb.execute("import socket\ns = socket.socket()"))
    # import shlex
    # from mcp import StdioServerParameters
    # parts = shlex.split("python mcp_tools_mbpp.py")
    # bridge = McpBridge(
    #     StdioServerParameters(command=parts[0], args=parts[1:]))
    # sb = Sandbox(SandboxConfig(authorized_imports=["json"]), bridge)
    # print(sb.execute(
    #     "code = 'def add(a, b):\\n    return a + b'\n"
    #     "print(run_tests(code, ['assert add(1, 2) == 3']))"))
    # print(sb.execute(
    #     "print(run_tests(code=code, test_list=['assert add(1, 2) == 4']))"))
    # print(sb.execute("print(run_tests(code))"))
    # sb.close()
    # bridge.close()
