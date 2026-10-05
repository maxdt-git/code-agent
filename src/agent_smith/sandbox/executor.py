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


@dataclass
class ExecutionResult:
    """
    Stock the result of the loop, including output, errors and
    final_answer if it found one
    """
    output: str
    error: str | None
    final_answer: str | None


class FinalAnswer(BaseException):
    """
    Raised by final answer to stop execution and keep answer
    """
    def __init__(self, answer: str) -> None:
        super().__init__(answer)
        self.answer = answer


def final_answer(answer: object) -> None:
    """
    Stop executiuon and give the best answer back to the agent
    """
    raise FinalAnswer(str(answer))


class Executor:
    """
    Class to execute the code, name_space is a dict of the
    precedent variable used
    """
    def __init__(self, config: SandboxConfig) -> None:
        self._name_space: dict[str, Any] = {}
        safe_import = make_safe_import(config.authorized_imports)
        safe_open = make_safe_open(config.allowed_directories)
        self._builtins = make_safe_builtins(
            safe_import, safe_open)

    def execute(self, code: str) -> ExecutionResult:
        """
        Execute the code and returns an Execution result
        """
        test_file = io.StringIO()
        error: str | None = None
        answer: str | None = None

        self._name_space["__builtins__"] = self._builtins
        self._name_space["__name__"] = "__sandbox__"
        self._name_space["final_answer"] = final_answer

        with redirect_stdout(test_file):
            try:
                tree = ast.parse(code, "<sandbox>")
                check_tree(tree)
                exec(compile(tree, "<sandbox>", "exec"), self._name_space)
            except FinalAnswer as e:
                answer = e.answer
            except Exception as e:
                error = "".join(traceback.format_exception(
                    type(e), e, e.__traceback__.tb_next if
                    e.__traceback__ else None
                ))

        text = test_file.getvalue()

        return ExecutionResult(text, error, answer)


if __name__ == "__main__":
    ex = Executor(SandboxConfig(authorized_imports=[
        "math", "collections", "collections.*"]))
    # print(ex.execute("print('avant')\nfinal_answer(
# 'done')\nprint('apres')"))
    # print(ex.execute("print('ok')\nprint(1 / 0)"))
    print(ex.execute("import os"))
    print(ex.execute("__import__('os')"))
    print(ex.execute("open('/etc/passwd')"))
    print(ex.execute("eval('1+1')"))
    print(ex.execute("import math\nprint(math.pi)"))
    print(ex.execute("class A: pass\nprint(A)"))
    print("=============")
    print(ex.execute("print(getattr((), '__class__'))"))
    print(ex.execute("print(getattr('abc', 'upper')())"))
    print(ex.execute("print(getattr('abc', 'nope', 42))"))
    print(ex.execute("print(hasattr('abc', 'upper'))"))
