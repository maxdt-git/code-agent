import os
import subprocess
import time

PULL_TIMEOUT = 600        # an image can weigh several GB
START_TIMEOUT = 60


class Container:
    """
    One SWE-bench container, tied to this process: it dies with it
    """
    def __init__(self, image: str, docker: str = "docker") -> None:
        self.image = image
        self.docker = docker
        self.name = f"agent_smith_{os.getpid()}"
        self._proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        """
        Start the container
        """
        # build the image
        done = subprocess.run([self.docker, "pull", self.image],
               capture_output=True, text=True, timeout=PULL_TIMEOUT)
        if done.returncode != 0:
            raise RuntimeError(done.stderr)

        self._proc = subprocess.Popen(
            [self.docker, "run", "-i", "--rm", "--name", self.name, self.image, "cat"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
