from dataclasses import dataclass
from typing import Any
import io
from contextlib import redirect_stdout
import traceback
from agent_smith.models import SandboxConfig
from agent_smith.sandbox.guards import (
    make_safe_import, make_safe_builtins, make_safe_open,
    check_tree)
import ast
from collections.abc import Callable


MAX_OUTPUT_CHARS = 10000


@dataclass
class ExecutionResult:
    """
    Stock the result of the loop, including output, errors and
    final_answer if it found one
    """
    output: str
    error: str | None
    final_answer: str | None
    timed_out: bool = False


class FinalAnswer(BaseException):
    """
    Raised by final answer to stop execution and keep answer
    """
    def __init__(self, answer: str) -> None:
        super().__init__(answer)
        self.answer = answer


class OutputStream(io.StringIO):
    """
    StringIO reports all written text to a callback
    """
    def __init__(
            self,
            on_output: Callable[[str], None] | None = None
    ) -> None:
        super().__init__()
        self._on_output = on_output
        # total of characters accepted since the start
        self._kept = 0
        # total of characters thrown away (over the limit)
        self._dropped = 0
        # True once the parent was told the output is truncated
        self._notified = False

    def truncate_message(self) -> str:
        """
        Keep the end of the text when it is longer than MAX_OUTPUT_CHARS
        """
        # nothing dropped -> no message, the output is complete
        if self._dropped == 0:
            return ""
        return (
            f"[output truncated: kept first {MAX_OUTPUT_CHARS} characters, "
            f"{self._dropped} more were dropped]"
        )

    def write(self, text: str) -> int:
        # room left before the limit
        rest = MAX_OUTPUT_CHARS - self._kept
        # part of this text that still fits ("" when rest is 0)
        kept = text[:rest]
        self._dropped += len(text) - len(kept)
        # first time something is dropped -> warn the parent, only once
        # needed for timeouts: execute() never ends, so truncate_message
        # is never added
        if self._dropped > 0 and self._notified is False:
            self._notified = True
            if self._on_output is not None:
                self._on_output(
                    f"[output truncated: limit of {MAX_OUTPUT_CHARS} "
                    "characters reached, the rest is dropped]"
                )

        if kept:
            self._kept += len(kept)
            # send to the parent (live output)
            if self._on_output is not None and text:
                self._on_output(kept)
            # store it -> read later with getvalue()
            super().write(kept)
        # print expects the full length, even if we dropped some
        return len(text)


def final_answer(answer: object) -> None:
    """
    Stop execution and give the best answer back to the agent
    """
    # an exception stops the code at once, wherever it is
    # FinalAnswer is a BaseException -> "except Exception" in the
    # code of the LLM cannot catch it by accident
    raise FinalAnswer(str(answer))


class Executor:
    """
    Class to execute the code, name_space is a dict of the
    precedent variable used
    """
    def __init__(
            self,
            config: SandboxConfig,
            on_output: Callable[[str], None] | None = None,
            tools: dict[str, Any] | None = None
    ) -> None:
        # globals of the executed code
        # kept between two execute() -> persistent variables
        self._name_space: dict[str, Any] = {}
        # build the restricted tools once, from the config
        safe_import = make_safe_import(config.authorized_imports)
        safe_open = make_safe_open(config.allowed_directories)
        self._builtins = make_safe_builtins(
            safe_import, safe_open)
        self._on_output = on_output
        self._tools = tools if tools is not None else {}

    def execute(self, code: str) -> ExecutionResult:
        """
        Execute the code and returns an Execution result
        """
        # new stream for each execution -> counters start at 0
        test_file = OutputStream(self._on_output)
        error: str | None = None
        answer: str | None = None

        # put back at each execution, in case the code replaced them
        # __builtins__ -> exec uses this dict instead of the real builtins
        self._name_space["__builtins__"] = self._builtins
        self._name_space["__name__"] = "__sandbox__"
        self._name_space.update(self._tools)
        self._name_space["final_answer"] = final_answer

        # every print of the code goes to test_file, not to the terminal
        with redirect_stdout(test_file):
            try:
                # 1. read the code without running it -> syntax tree
                tree = ast.parse(code, "<sandbox>")
                # 2. refuse forbidden names/attributes before running
                check_tree(tree)
                # 3. run it with our namespace and our builtins
                exec(compile(tree, "<sandbox>", "exec"), self._name_space)
            except FinalAnswer as e:
                answer = e.answer
            # Exception only -> KeyboardInterrupt and SystemExit
            # are not caught here
            except Exception as e:
                # tb_next -> skip the first frame (this file)
                # so the LLM only sees the lines of its own code
                error = "".join(traceback.format_exception(
                    type(e), e, e.__traceback__.tb_next if
                    e.__traceback__ else None
                ))

        # what the code printed + the truncation message if any
        text = test_file.getvalue() + test_file.truncate_message()

        return ExecutionResult(text, error, answer)


# if __name__ == "__main__":
#     ex = Executor(SandboxConfig(authorized_imports=[
#         "math", "collections", "collections.*"]))
#     # print(ex.execute("print('avant')\nfinal_answer(
# # 'done')\nprint('apres')"))
#     # print(ex.execute("print('ok')\nprint(1 / 0)"))
#     print(ex.execute("import os"))
#     print(ex.execute("__import__('os')"))
#     print(ex.execute("open('/etc/passwd')"))
#     print(ex.execute("eval('1+1')"))
#     print(ex.execute("import math\nprint(math.pi)"))
#     print(ex.execute("class A: pass\nprint(A)"))
#     print("=============")
#     print(ex.execute("print(getattr((), '__class__'))"))
#     print(ex.execute("print(getattr('abc', 'upper')())"))
#     print(ex.execute("print(getattr('abc', 'nope', 42))"))
#     print(ex.execute("print(hasattr('abc', 'upper'))"))
    # print("======== test truncate")
    # ex = Executor(SandboxConfig())
    # r = ex.execute("print('a' * 50_000)")
    # print(len(r.output))
    # print(r.output)
    # r = ex.execute("print('hello')")
    # print(repr(r.output))
