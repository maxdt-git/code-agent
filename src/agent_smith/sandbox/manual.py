from typing import Any
from agent_smith.models import SandboxConfig


JSON_TYPES = {
    "string": "str", "integer": "int", "number": "float", "boolean": "bool",
    "object": "dict", "null": "None"
}


def type_name(schema: dict[str, Any]) -> str:
    """
    Python like name of a JSON schema type
    """
    # mean one of this type(eg int | None)
    if "anyOf" in schema:
        return " | ".join(type_name(option) for option in schema["anyOf"])
    kind = schema.get("type")
    if kind == "array":
        items = schema.get("items")
        return f"list[{type_name(items)}]" if items is not None else "list"
    # simple types are in the dict else its just Any
    return JSON_TYPES.get(str(kind), "Any")


def signature(tool: Any) -> str:
    """
    One tool as a python signature, built from him input_schema
    """
    # get schema and dict where the parameters are
    schema = tool.inputSchema
    # we read the list of necessary parameters
    required = schema.get("required", [])
    # stock all parameters inside
    params: list[str] = []

    for name, prop in schema.get("properties", {}).items():
        param = f"{name}: {type_name(prop)}"
        if name not in required:
            param += f" = {prop.get('default')!r}"
        params.append(param)
    return f"{tool.name}({', '.join(params)}) -> str"


def build_manual(tools: list[Any], config: SandboxConfig) -> str:
    """
    Text given to the LLM: sandbox rules and the available functions
    """
    lines = [
        "SANDBOX MANUAL",
        "Your Python code runs in a restricted sandbox.",
        "- Variables, functions and imports persist between steps.",
        "- Allowed imports: " + ", ".join(config.authorized_imports),
        "- File access only inside: "
        + (", ".join(config.allowed_directories) or "nowhere"),
        f"- Time limit: {config.max_execution_time_seconds} s per step. "
        f"Memory limit: {config.max_memory_mb} MB.",
        "- No network. eval, exec, open outside allowed directories and "
        "__dunder__ attributes are forbidden.",
        "- Use print() to see values: only printed text is returned to you.",
        "",
        "AVAILABLE FUNCTIONS (call them directly, no import needed)",
    ]
    for tool in tools:
        lines.append(signature(tool))
        description = (tool.description or "").strip()
        for line in description.splitlines():
            lines.append("    " + line.strip())
    lines.append("final_answer(answer: str) -> None")
    lines.append("    Submit your final answer and end the task.")
    return "\n".join(lines)


# if __name__ == "__main__":
#     import shlex
#     from mcp import StdioServerParameters
#     from agent_smith.sandbox.mcp_bridge import McpBridge
#     parts = shlex.split("python mcp_tools_mbpp.py")
#     bridge = McpBridge(
#         StdioServerParameters(command=parts[0], args=parts[1:]))
#     print(build_manual(bridge.list_tools(), SandboxConfig(
#         authorized_imports=["math", "re"],
#         allowed_directories=["/tmp/agent"])))
#     bridge.close()
