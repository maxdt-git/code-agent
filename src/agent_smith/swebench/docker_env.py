import os
import subprocess
import time
import shlex

PULL_TIMEOUT = 600
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
        Download the image, start the container and wait until it runs
        """
        # download the image, nothing if already up to date
        try:
            done = subprocess.run([self.docker, "pull", self.image],
                                  capture_output=True, text=True,
                                  timeout=PULL_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"docker pull took more than {PULL_TIMEOUT} s")
        if done.returncode != 0:
            raise RuntimeError(f"docker pull failed: {done.stderr.strip()}")

        # cat read our stdin forever: when this process dies,
        # the pipe closes, cat exits, and --rm removes the container
        self._proc = subprocess.Popen(
            [self.docker, "run", "-i", "--rm", "--name", self.name,
             self.image, "cat"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)

        # Popen returns at once: wait until docker says it is running
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            state = subprocess.run(
                [self.docker, "inspect", "-f", "{{.State.Running}}",
                 self.name], capture_output=True, text=True)
            if state.stdout.strip() == "true":
                return
            # docker run already ended -> the start failed, no need to wait
            if self._proc.poll() is not None:
                break
            time.sleep(0.2)
        self.stop()
        raise RuntimeError(f"container {self.name} did not start")

    def write_file(self, path: str, content: str) -> None:
        """
        Write a file inside the container (creates its folder)
        """
        # the content goes through stdin, like edit_file does
        command = (f"mkdir -p {shlex.quote(os.path.dirname(path))} "
                   f"&& cat > {shlex.quote(path)}")
        done = subprocess.run(
            [self.docker, "exec", "-i", self.name, "bash", "-c", command],
            input=content, capture_output=True, text=True, timeout=30)
        if done.returncode != 0:
            raise RuntimeError(f"cannot write {path}: {done.stderr.strip()}")

    def stop(self) -> None:
        """
        Remove the container
        """
        if self._proc is not None:
            # closing stdin ends cat: the container stops, --rm removes it
            if self._proc.stdin is not None:
                self._proc.stdin.close()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        # safety net: force removal, ignore "no such container"
        subprocess.run([self.docker, "rm", "-f", self.name],
                       capture_output=True)
