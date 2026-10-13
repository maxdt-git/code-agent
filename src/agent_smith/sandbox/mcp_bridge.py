import asyncio
import threading
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from typing import Any


# mcp Client
# -> open mcp connect (async with Client(...))
# -> list tools and call tools
# StdioServerParameters -> command - program to laucnh
# and args (mcp_tools_mbpp.py)
# pass to Client -> describe commands who launch the server

# Event() -> create a flag
# .wait() -> wait for the flag to be raise
# .set() -> raise the flag


class McpBridge:
    """
    Synchronous access to an MCP server, from a background event loop
    """
    def __init__(self, target: StdioServerParameters | str) -> None:
        self._target = target
        # create the event loop
        self._loop = asyncio.new_event_loop()
        # one wait with wait and other calls set
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._client: ClientSession | None = None
        # second thread of the same process -> self._run
        # daemon=True -> stop when program ends
        self._thread = threading.Thread(
            target=self._run, daemon=True
        )
        self._thread.start()
        # block until not raise
        # when mcp bridge give back hand, either connec ready or error
        self._ready.wait()
        if self._error is not None:
            raise RuntimeError(
                f"cannot connect to mcp server: {self._error}"
            )

    def _run(self) -> None:
        """
        Thread body -> run the event loop until the connection is closed
        """
        asyncio.set_event_loop(self._loop)
        # run the loop until serve is done
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        """
        Keep the mcp connection open until close is called
        """
        self._stop = asyncio.Event()
        try:
            # open the connection
            # laucnh the server as a subprocess
            # AsyncExitStack keep multiple connec open
            # closethem in other order
            async with AsyncExitStack() as stack:
                # streamable connect to an already launch serv
                if isinstance(self._target, str):
                    read, write, _ = await stack.enter_async_context(
                        streamable_http_client(self._target)
                    )
                else:
                    # stdio_client launch the command as subprocess
                    # and connect to it entry and standard output
                    read, write = await stack.enter_async_context(
                        stdio_client(self._target)
                    )
                session = await stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
                self._client = session
                # when the connec is ready, raise the flag
                # who deblocks constructor
                self._ready.set()
                # put _serve in pause
                # open until close
                await self._stop.wait()
        # if connec failed
        # get the error and also raise flag or it wait for ever
        except BaseException as e:
            self._error = e
            self._ready.set()

    def _call(self, corou: Any) -> Any:
        """
        Run a coroutine on the backround loop and wait for its result
        """
        future = asyncio.run_coroutine_threadsafe(corou, self._loop)
        # a ticket who represents the coming answer
        return future.result()

    def list_tools(self) -> list[Any]:
        """
        Tools exposed by the server (name, description, input_schema)
        """
        # for mypy because could be Client or None
        assert self._client is not None
        # create the routine then execute it with _call
        # response is an object in tools
        result = self._call(self._client.list_tools())
        return list(result.tools)

    def call_tool(
            self,
            name: str,
            arguments: dict[str, Any]
    ) -> str:
        """
        Call one tool and return its text output
        """
        # mcp protocol gives all arguments by name in a dict
        assert self._client is not None
        result = self._call(self._client.call_tool(name, arguments))
        return "\n".join(
            item.text for item in result.content if hasattr(item, "text")
        )

    def close(self) -> None:
        """
        Close the connection and stop the background thread
        """
        # ask the loop to call stop in his fil
        # when stop is raise, serve stop the pause and leave bloc async with
        # -> it close the conn and the serv all the fil is done
        self._loop.call_soon_threadsafe(self._stop.set)
        # wait 5sec the fil is really done
        self._thread.join(timeout=5)

    def _listing(
            self,
            corou: Any,
            field: str
    ) -> list[Any]:
        """
        Run a list request, an empty list if the server does not support it
        """
        try:
            return list(getattr(self._call(corou), field))
        except Exception:
            return []

    def list_resources(self) -> list[Any]:
        """
        Resources of the server (uri, name, description)
        """
        assert self._client is not None
        return self._listing(self._client.list_resources(), "resources")

    def list_resource_templates(self) -> list[Any]:
        """
        Resource templates of the server (uri_template, name, description)
        """
        assert self._client is not None
        return self._listing(
            self._client.list_resource_templates(), "resourceTemplates")

    def list_prompts(self) -> list[Any]:
        """
        Prompts of the server (name, description, arguments)
        """
        assert self._client is not None
        return self._listing(self._client.list_prompts(), "prompts")


# if __name__ == "__main__":
#     import shlex
#     parts = shlex.split("python mcp_tools_mbpp.py")
#     bridge = McpBridge(
#         StdioServerParameters(command=parts[0], args=parts[1:]))
#     print("connected:", bridge._client is not None)
#     for tool in bridge.list_tools():
#         print(tool.name)
#         print(tool.input_schema)
#     print("========", bridge.call_tool("run_tests", {
#         "code": "def add(a, b):\n    return a + b",
#         "test_list": ["assert add(1, 2) == 3"]}))
#     print("========", bridge.call_tool("run_tests", {
#         "code": "def add(a, b):\n    return a - b",
#         "test_list": ["assert add(1, 2) == 3"]}))
#     bridge.close()
#     print("thread alive:", bridge._thread.is_alive())
