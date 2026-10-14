import ast
import json
from dataclasses import dataclass
from typing import Any


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
    except SyntaxError:
        return False
    kinds = (ast.Call, ast.Assign, ast.FunctionDef, ast.Import, ast.ImportFrom)
    return any(isinstance(node, kinds) for node in ast.walk(tree))


def python_block(text: str) -> tuple[str, bool] | None:
    """
    Code of the first ``` block, none in there is no block
    True if closed else False
    """
    start = text.find("```")
    if start == -1:
        return None
    start_end = text.find("\n", start)
    if start_end == -1:
        return None
    end = text.find("```", start_end)
    if end == -1:
        return text[start_end + 1:].strip(), False
    return text[start_end + 1:end].strip(), True


def between(
        text: str,
        left: str,
        right: str,
        start: int = 0
) -> tuple[str, int] | None:
    """
    Text between left and right, none when one of them is missing
    """
    begin = text.find(left, start)
    if begin == -1:
        return None
    begin += len(left)

    end = text.find(right, begin)
    if end == -1:
        return None
    return text[begin:end], end + len(right)


def xml_block(text: str) -> tuple[str, dict[str, Any]] | None:
    """
    Tool name and arguments of
    <invoke name="tool"><parameter name="p">v</parameter></invoke>
    """
    found = between(text, 'invoke name="', '"')
    if not found:
        return None
    name, after = found

    body = between(text, ">", "</invoke>", after)
    if body is None:
        return None

    content = body[0]
    arguments: dict[str, Any] = {}
    position = 0

    while True:
        param = between(content, '<parameter name="', '"', position)
        if param is None:
            break

        key, position = param
        value = between(content, ">", "</parameter>", position)
        if value is None:
            break

        arguments[key] = parse_value(value[0].strip())
        position = value[1]

    return name, arguments


def json_block(text: str) -> str | None:
    """
    Json text of <tool_call>{...}</tool_call>
    """
    start = text.find("<tool_call>")
    if start == -1:
        return None

    start += len("<tool_call>")
    end = text.find("</tool_call>", start)

    return text[start:] if end == -1 else text[start:end]


def react_block(text: str) -> tuple[str, Any] | None:
    """
    Tool and args of Atcion: Tool and Action input: {...}
    """
    start = text.find("Action:")
    middle = text.find("Action Input:")
    if start == -1 or middle == -1 or middle < start:
        return None

    name = text[start + len("Action:"):middle].strip()
    return name, parse_value(text[middle + len("Action Input:"):].strip())


def extract_code(text: str) -> Extraction:
    """
    Return the code to execute and if needed how it was interpreted
    """
    pyt_block = python_block(text)
    if pyt_block is not None and pyt_block[0]:
        code, closed = pyt_block
        if closed:
            return Extraction(code)
        return Extraction(
            code,
            "Your code was not closed with ```. Everything after "
            "the opening ``` was executed as code."
        )

    xml = xml_block(text)
    if xml is not None:
        code = to_call(*xml)
        return Extraction(
            code,
            "Your xml tool was converted to python: "
            + code.splitlines()[0]
        )

    js_block = json_block(text)
    if js_block is not None:
        try:
            data = json.loads(js_block)
            code = to_call(data["name"], data.get("arguments") or {})
        except (ValueError, KeyError, TypeError, AttributeError):
            return Extraction(
                None,
                "Your <tool_call> is not valid JSON with a 'name' and "
                "'arguments'. Write a ```python block instead."
            )
        return Extraction(
            code,
            "Your JSON tool was converted to python: "
            + code.splitlines()[0]
        )

    react = react_block(text)
    if react is not None and react[0].isidentifier():
        name, value = react
        if isinstance(value, dict):
            code = to_call(name, value)
        else:
            code = to_call(name, {})
        return Extraction(
            code,
            "Your Action/Action Input was converted to python: "
            + code.splitlines()[0]
        )

    if is_python(text.strip()):
        return Extraction(
            text.strip(),
            "No ``` code block found: your whole answer was executed as python"
        )

    return Extraction(
        None,
        "No code found in your answer. Reply with one ```python block "
        "ending with <end_code>."
    )


if __name__ == "__main__":
    print(between(
        "<invoke name='tool'><parameter name='p'>v</parameter></invoke>",
        "parameter name='", "'"))

    for text in [
        "Thought: test.\n```python\nx = 1\nprint(x)\n```<end_code>",
        "Let me try\n```python\nprint(3)",
        '<invoke name="read_file"><parameter name="filepath">a.py'
        '</parameter><parameter name="start_line">1</parameter></invoke>',
        '<tool_call>{"name": "ping", "arguments": {}}',
        "Action: read_file\nAction Input: {\"filepath\": \"a.py\"}",
        "I am not sure what to do next.",
    ]:
        print(extract_code(text))
