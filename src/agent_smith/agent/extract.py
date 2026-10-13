import ast
import json
import re
from dataclasses import dataclass
from typing import Any


CLOSED_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)

OPEN_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*)", re.DOTALL)

INVOKE = re.compile(r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', re.DOTALL)

PARAMETER = re.compile(
    r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.DOTALL)

TOOL_CALL = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*(?:</tool_call>|$)", re.DOTALL)

REACT = re.compile(
    r"Action:\s*([A-Za-z_]\w*)\s*\n\s*Action Input:\s*(.*)", re.DOTALL)


@dataclass
class Extraction:
    """
    Code found in a model response, with a note for the model when the
    response was not a clean Python block
    """
    # code to execute or none
    code: str | None
    # message for the model, or none if answer is clean
    note: str | None = None


def to_call(
        name: str,
        arguments: dict[str, Any]
) -> str:
    """
    Python code calling one tool and printing its result
    """
    args = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    return f"result = {name}({args})\nprint(result)"


def parse_value(text: str) -> Any:
    """
    A parameter written as text: JSON when possible else raw str
    """
    try:
        return json.loads(text)
    except ValueError:
        return text


def is_python(text: str) -> bool:
    """
    True when the text is valid python that does something
    """
    try:
        tree = ast.parse(text)
    except:
        return False
    kinds = (ast.Call, ast.Assign, ast.FunctionDef, ast.Import, ast.ImportFrom)
    return any(isinstance(node, kinds) for node in ast.walk(tree))


def extract_code(text: str) -> Extraction:
    """
    Return the code to execute and if needed how it was interpreted
    """
    match = CLOSED_BLOCK.search(text)
    if match:
        return Extraction(match.group(1).strip())

    match = OPEN_BLOCK.search(text)
    if match and match.group(1).strip():
        return Extraction(
            match.group(1).strip(),
            "Your code block was not closed with ```. Everything after "
            "the opening ``` was executed as code."
        )
