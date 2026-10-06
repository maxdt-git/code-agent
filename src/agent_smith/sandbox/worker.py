from agent_smith.models import SandboxConfig
from agent_smith.sandbox.executor import Executor
from multiprocessing.connection import Connection
import os
import resource
import socket
from typing import Any


def worker_main(
        conn: Connection,
        config: SandboxConfig,
) -> None:
    """
    Child process loop, receive code and send back result
    """
    def send_output(text: str) -> None:
        conn.send(("output", text))

    execute = Executor(config, on_output=send_output)
    limit_memory(config.max_memory_mb)
    block_network()
    while True:
        try:
            code = conn.recv()
        except EOFError:
            break
        result = execute.execute(code)
        conn.send(("result", result))


def limit_memory(max_memory_mb: int) -> None:
    """
    Cap the process memory to current_size + max_memory_nb
    """
    # get the size of a page
    # generally 4096 octets
    page_size = os.sysconf("SC_PAGE_SIZE")
    # create the content of this file
    # take only [0] -> correspond to the number of pages total_size
    with open("/proc/self/statm") as f:
        current = int(f.read().split()[0]) * page_size
    limit = current + max_memory_mb * 1024 * 1024
    # fix the limit
    # if code ask for more, MemoryError
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


class BlockedSocket(socket.socket):
    """
    Socket replacement that refuses to be created
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise PermissionError("network access not allowed in the sandbox")


def block_network() -> None:
    """
    Make every socket creation fail
    """
    socket.socket = BlockedSocket  # type: ignore[misc]
