import sys
from pathlib import Path

from agent_smith.models import SWEBenchTaskInput
from agent_smith.swebench.docker_env import Container

EVAL_PATH = "/tmp/agent/eval.sh"

if __name__ == "__main__":
    task = SWEBenchTaskInput.model_validate_json(Path(sys.argv[1]).read_text())
    container = Container(task.docker_image)
    container.start()
    container.write_file(EVAL_PATH, task.eval_script)
    print(f"SWEBENCH_CONTAINER={container.name} EVAL_SCRIPT={EVAL_PATH}")
    try:
        input("Container ready. Press Enter to remove it...")
    finally:
        container.stop()
