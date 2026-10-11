from agent_smith.models import SandboxConfig
from agent_smith.sandbox.executor import Executor
from multiprocessing.connection import Connection
import os
import resource
import socket
from typing import Any
import signal


def worker_main(
        conn: Connection,
        config: SandboxConfig,
) -> None:
    """
    Child process loop, receive code and send back result
    """
    # the child inherits the parent env (API keys...) -> empty it
    os.environ.clear()
    # get the keyboard interrupt -> ctrl + C
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # callback given to the executor
    # each print of the code is sent right away to the parent
    # ("output", text) -> partial output, kept if the code times out
    def send_output(text: str) -> None:
        conn.send(("output", text))

    # one executor for the whole life of the child
    # -> variables stay between two executions
    execute = Executor(config, on_output=send_output)
    # limits are set after our own imports
    # so they only apply to the code we run
    limit_memory(config.max_memory_mb)
    block_network()

    while True:
        # wait for the next code sent by the parent
        # EOFError -> parent closed the pipe -> stop the child
        try:
            code = conn.recv()
        except EOFError:
            break
        try:
            result = execute.execute(code)
        except (SystemExit, KeyboardInterrupt) as e:
            # catch an error from the child
            conn.send(("raise", e))
            continue
        # ("result", ...) -> execution is over, parent stops waiting
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
    # creating a socket is the first step of any connection
    # failing here blocks both outbound and inbound network
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise PermissionError("network access not allowed in the sandbox")


def block_network() -> None:
    """
    Make every socket creation fail
    """
    # second barrier after the import allowlist
    # replace the class for the whole child process
    # -> even an authorized module cannot open a connection
    socket.socket = BlockedSocket  # type: ignore[misc]
