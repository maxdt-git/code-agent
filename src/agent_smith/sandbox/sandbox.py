import multiprocessing
from agent_smith.models import SandboxConfig
from agent_smith.sandbox.worker import worker_main
from agent_smith.sandbox.executor import ExecutionResult
import time


class Sandbox:
    """
    Run code in a child process
    """
    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
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
            args=(child_conn, self._config),
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
                self.restart()
                return ExecutionResult(
                    output="".join(chunks),
                    error=(
                        f"The sandbox process died, probably because it"
                        f"exceed the memory limit {self._config.max_memory_mb}"
                        ".\nThe sandbox was restarted: all variables, "
                        "functions and import from previous steps are lost"
                    ),
                    final_answer=None,
                    timed_out=True
                )
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
        self.restart()
        return ExecutionResult(
                output="".join(chunks),
                error=(
                    f"Execution timed out after {limit} seconds and"
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

    def restart(self) -> None:
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
