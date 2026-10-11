from collections.abc import Callable
from typing import Any
import builtins
import os
import ast
import types


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

FORBIDDEN_MODULE_NAMES = (
    "attrgetter", "methodcaller"
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
        # "collections.*" -> allows the submodules of collections
        if key.endswith(".*"):
            # remove only the "*" and keep the dot: "collections."
            # -> "collections.abc" matches, "collectionsX" does not
            prefix = key[:-1]
            if name.startswith(prefix):
                return True
        elif key == name:
            return True
    # everything not listed is refused
    return False


def make_safe_import(authorized: list[str]) -> Callable[..., Any]:
    """
    Build the __import__ replacement with only allowed modules
    """
    # same parameters as the real __import__
    # python calls it for every "import x" / "from x import y"
    def safe_import(
            name: str,
            globals: Any = None,
            locals: Any = None,
            fromlist: Any = (),
            level: int = 0
            ) -> Any:
        # level > 0 -> relative import (from . import x), never allowed
        if level > 0 or not is_allowed(name, authorized):
            raise ImportError(f"import of '{name}' is not allowed")
        # the real import -> the full module
        module = builtins.__import__(name, globals, locals, fromlist, level)
        # the code only gets a filtered copy, never the real module
        return make_safe_module(module, authorized)

    # safe_import remembers "authorized" (closure)
    return safe_import


def is_allowed_path(real: str, allowed_directories: list[str]) -> bool:
    """
    Check if real is in allowed directories
    """
    for d in allowed_directories:
        # resolve the allowed directory too
        base = os.path.realpath(d)
        # the directory itself, or something inside it
        # base + "/" -> "/tmp/agent_other" is not inside "/tmp/agent"
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
        # open -> a file descriptor number, no path to check
        if not isinstance(file, str):
            raise PermissionError("opening a file descriptor is not allowed")
        # real path -> ".." and symlinks are resolved before the check
        real = os.path.realpath(file)
        if not is_allowed_path(real, allowed_directories):
            raise PermissionError(f"access to '{file}' is not allowed")
        # open the resolved path, the one we checked
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
    # check_tree only sees names written in the code
    # here the name is a string built at runtime -> check it now
    # same idea for setattr, delattr and hasattr below
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


def make_safe_builtins(
        safe_import: Callable[..., Any],
        safe_open: Callable[..., Any]
 ) -> dict[str, Any]:
    """
    Build the authorized buildins by removind the forbidden ones
    """
    # dict with all base function
    # dict(...) -> a copy, the real builtins are not modified
    safe = dict(vars(builtins))

    # pop(name, None) -> no error if the name does not exist
    for name in FORBIDDEN_BUILTINS:
        safe.pop(name, None)

    # replace the ones we want to keep, but under control
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
    # __x__ names give access to python internals
    # all refused, except the few harmless ones we list
    if name.startswith("__") and name.endswith("__") \
            and name not in ALLOWED_DUNDERS:
        return True
    # other internal names (frames...) that are not dunders
    return name in FORBIDDEN_ATTR


def make_safe_module(
        module: types.ModuleType,
        authorized: list[str]
) -> types.ModuleType:
    """
    Copy of a modulekeeping only public so imported module
    cannot import os, sys or codecs
    """
    # new empty module with the same name
    safe = types.ModuleType(module.__name__)

    # vars(module) -> every name defined in the real module
    for name, value in vars(module).items():
        # private names are not part of the public API
        if name.startswith("_"):
            continue
        # a module imports other modules for its own use
        # they would be reachable as attributes -> skip them
        if isinstance(value, types.ModuleType):
            # value.__name__ -> full name, like "collections.abc"
            if not is_allowed(value.__name__, authorized):
                continue
            # allowed submodule -> keep it, filtered the same way
            value = make_safe_module(value, authorized)
        # functions reading an attribute from a string name
        # they would skip check_tree and safe_getattr
        if name in FORBIDDEN_MODULE_NAMES:
            continue
        # same as safe.<name> = value, with the name in a variable
        setattr(safe, name, value)

    return safe


def check_tree(tree: ast.AST) -> None:
    """
    Raise SandboxViolation if the code touch forbidenn name or attributes
    """
    # ast.walk -> every node of the tree
    # the code is only read here, nothing is executed yet
    for node in ast.walk(tree):
        # x.name -> node.attr is "name"
        if isinstance(node, ast.Attribute) and is_forbidden_attr(node.attr):
            raise SandboxViolation(
                f"access to attribute '{node.attr}' is not allowed"
            )
        # a bare name -> node.id
        if isinstance(node, ast.Name) and is_forbidden_attr(node.id):
            raise SandboxViolation(
                f"use of name '{node.id}' is not allowed"
            )
        # match x: case C(name=v) -> also reads x.name
        # the names are plain strings in kwd_attrs, not Attribute nodes
        if isinstance(node, ast.MatchClass):
            for attr in node.kwd_attrs:
                if is_forbidden_attr(attr):
                    raise SandboxViolation(
                        f"attribute '{attr}' in a match pattern is not allowed"
                    )


# if __name__ == "__main__":
#     print(is_allowed("va.pypy", ["yo", "ca", "va.pypy", ""]))
#     safe_import = make_safe_import(["math", "eval", "max"])
#     safe = make_safe_builtins(safe_import)
#     print("math" in safe)
