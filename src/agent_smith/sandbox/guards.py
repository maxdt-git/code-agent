from collections.abc import Callable
from typing import Any
import builtins
import os
import ast


# block eval exec compile -> exec code
# block open -> read or write on file
# block globals, locals, var -> look in namespace and find ancient builtins
# block input, breakpoint, help -> block program until write
# exit quit -> raise SystemExit -> forbidden
FORBIDDEN_BUILTINS = (
    "eval", "exec", "compile", "open", "input", "breakpoint",
    "globals", "locals", "vars", "exit", "quit", "help"
)

# block other route to builtin
FORBIDDEN_ATTR = (
    "gi_frame", "gi_code", "cr_frame", "ag_frame", "tb_frame",
    "f_globals", "f_builtins", "f_locals", "f_back", "f_code",
    "func_globals", "sys", "os", "modules"
)

ALLOWED_DUNDERS = (
    "__init__", "__name__", "__doc__"
)


class SandboxViolation(Exception):
    """
    Raised when the code uses a forbidden construct
    """


def is_allowed(name: str, authorized: list[str]) -> bool:
    """
    Test if the import is authorized
    """
    for key in authorized:
        if key.endswith(".*"):
            prefix = key[:-1]
            if name.startswith(prefix):
                return True
        elif key == name:
            return True
    return False


def make_safe_import(authorized: list[str]) -> Callable[..., Any]:
    """
    Build the __import__ replacement with only allowed modules
    """
    def safe_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: Any = (),
            level: int = 0
            ) -> Any:
        if level > 0 or not is_allowed(name, authorized):
            raise ImportError(f"import of '{name}' is not allowed")
        return builtins.__import__(name, globals, locals, fromlist, level)

    return safe_import


def is_allowed_path(real: str, allowed_directories: list[str]) -> bool:
    """
    Check if real is in allowed directories
    """
    for d in allowed_directories:
        base = os.path.realpath(d)
        if real == base or real.startswith(base + os.sep):
            return True

    return False


def make_safe_open(allowed_directories: list[str]) -> Callable[..., Any]:
    """
    Create the safe_open func
    """
    def safe_open(
        file: str | Any,
        mode: str = "r",
        *args: Any,
        **kwargs: Any
    ) -> Any:
        if not isinstance(file, str):
            raise PermissionError("opening a file descriptor is not allowed")
        real = os.path.realpath(file)
        if not is_allowed_path(real, allowed_directories):
            raise PermissionError(f"access to '{file}' is not allowed")
        return builtins.open(
            real, mode, *args, **kwargs
        )

    return safe_open


def safe_getattr(
        obj: Any,
        name: str,
        *default: Any
) -> Any:
    """
    Safe getattr and raise a SandboxViolation if name is forbidden
    """
    if is_forbidden_attr(name):
        raise SandboxViolation(
            f"access to attribute name '{name}' is not allowed"
        )
    return getattr(obj, name, *default)


def safe_setattr(
        obj: Any,
        name: str,
        value: Any
) -> Any:
    """
    Safe setattr and raise a SandboxViolation if name is forbidden
    """
    if is_forbidden_attr(name):
        raise SandboxViolation(
            f"access to attribute name '{name}' is not allowed"
        )
    return setattr(obj, name, value)


def safe_delattr(
        obj: Any,
        name: str,
) -> Any:
    """
    Safe delattr and raise a SandboxViolation if name is forbidden
    """
    if is_forbidden_attr(name):
        raise SandboxViolation(
            f"access to attribute name '{name}' is not allowed"
        )
    return delattr(obj, name)


def safe_hasattr(
        obj: Any,
        name: str,
) -> Any:
    """
    Safe hasattr and raise a SandboxViolation if name is forbidden
    """
    if is_forbidden_attr(name):
        raise SandboxViolation(
            f"access to attribute name '{name}' is not allowed"
        )
    return hasattr(obj, name)


def make_safe_builtins(safe_import: Callable[..., Any],
                       safe_open: Callable[..., Any]) -> dict[str, Any]:
    """
    Build the authorized buildins by removind the forbidden ones
    """
    # dict with all base function
    safe = dict(vars(builtins))

    for name in FORBIDDEN_BUILTINS:
        safe.pop(name, None)

    safe["__import__"] = safe_import
    safe["open"] = safe_open
    safe["getattr"] = safe_getattr
    safe["setattr"] = safe_setattr
    safe["delattr"] = safe_delattr
    safe["hasattr"] = safe_hasattr

    return safe


def is_forbidden_attr(name: str) -> bool:
    """
    Check if the attributes is autorized
    """
    if name.startswith("__") and name.endswith("__") \
            and name not in ALLOWED_DUNDERS:
        return True
    return name in FORBIDDEN_ATTR


def check_tree(tree: ast.AST) -> None:
    """
    Raise SandboxViolation if the code touch forbidenn name or attributes
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and is_forbidden_attr(node.attr):
            raise SandboxViolation(
                f"access to attribute '{node.attr}' is not allowed"
            )
        if isinstance(node, ast.Name) and is_forbidden_attr(node.id):
            raise SandboxViolation(
                f"use of name '{node.id}' is not allowed"
            )


# if __name__ == "__main__":
#     print(is_allowed("va.pypy", ["yo", "ca", "va.pypy", ""]))
#     safe_import = make_safe_import(["math", "eval", "max"])
#     safe = make_safe_builtins(safe_import)
#     print("math" in safe)
