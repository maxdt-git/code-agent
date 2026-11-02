"""
Compute the tables of BENCHMARK_REPORT.md from benchmark/*.json
Usage: uv run python scripts/bench_report.py
"""
import json
import re
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1] / "benchmark"
# <task>__<model>__run<label>.json, label like "1" or "2-section"
NAME = re.compile(
    r"^(?P<task>[^_]+(?:-[^_]+)*)__(?P<model>.+)__run(?P<run>[\w-]+)\.json$")


def verdict(path: Path) -> str:
    """
    PASS/FAIL from the saved moulinette validation, '?' if not validated
    """
    val = Path(str(path) + ".validation.txt")
    if not val.exists():
        return "?"
    text = val.read_text()
    if "Overall: PASSED" in text:
        return "PASS"
    return "FAIL" if "Overall: FAILED" in text else "?"


def patched_files(patch: str) -> list[str]:
    """
    Files changed by a git patch (paths relative to the repository)
    """
    return re.findall(r"^diff --git a/(\S+)", patch, re.MULTILINE)


def first_step(steps: list[dict], test) -> int | None:
    """
    Number of the first step whose code matches test, None if none does
    """
    for s in steps:
        if test(s):
            return int(s["step"])
    return None


def tests_pass(observation: str) -> bool:
    """
    Heuristic: the run_tests output reports passing tests and no failure
    """
    low = observation.lower()
    return "passed" in low and not re.search(r"\b(failed|error)\b", low)


def analyse(path: Path) -> dict:
    """
    All metrics of one run
    """
    m = NAME.match(path.name)
    assert m is not None, path.name
    d = json.loads(path.read_text())
    steps = d["steps"]
    files = patched_files(d["solution"])
    times = [s["request_time_ms"] for s in steps]
    test_steps = [int(s["step"]) for s in steps
                  if "run_tests(" in s["sandbox_input"]
                  and tests_pass(s["sandbox_output"])]
    final = first_step(steps, lambda s: "final_answer(" in s["sandbox_input"])
    return {
        "task": m["task"], "model": m["model"], "run": m["run"],
        "pass": verdict(path),
        "models_used": sorted({s["model_name"] for s in steps}),
        "iterations": d["iterations"],
        "input": d["total_input_tokens"], "output": d["total_output_tokens"],
        "time": d["total_time_seconds"],
        "requests": d["total_requests"],
        "retries": sum(s["retries"] for s in steps),
        "avg_request_s": sum(times) / len(times) / 1000 if times else None,
        "error": d["error"] or "",
        "first_touch": first_step(steps, lambda s: any(
            f in s["sandbox_input"] for f in files)) if files else None,
        "first_edit": first_step(steps, lambda s: "edit_file(" in s[
            "sandbox_input"] and any(f in s["sandbox_input"] for f in files))
        if files else None,
        "first_tests_pass": test_steps[0] if test_steps else None,
        "final_answer": final,
        "no_code_answers": sum("No code found" in s["sandbox_output"]
                               for s in steps),
    }


def fmt(value: object) -> str:
    """
    Table cell: '-' for missing values
    """
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


if __name__ == "__main__":
    runs = [analyse(p) for p in sorted(BENCH.glob("*__run*.json"))]
    print("| Model | Task | Pass | Iterations | Input tokens | Output tokens "
          "| Time (s) | Requests | Retries | Avg request (s) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(runs, key=lambda r: (r["model"], r["task"])):
        print(f"| {r['model']} | {r['task']} | {r['pass']} | "
              f"{r['iterations']} | {r['input']:,} | {r['output']:,} | "
              f"{fmt(r['time'])} | {r['requests']} | {r['retries']} | "
              f"{fmt(r['avg_request_s'])} |")
    print()
    print("| Model | Task | First read/edit of patched file | First edit "
          "| First passing run_tests | final_answer | Answers without code "
          "| Models used | Error |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(runs, key=lambda r: (r["model"], r["task"])):
        print(f"| {r['model']} | {r['task']} | {fmt(r['first_touch'])} | "
              f"{fmt(r['first_edit'])} | {fmt(r['first_tests_pass'])} | "
              f"{fmt(r['final_answer'])} | {r['no_code_answers']} | "
              f"{', '.join(r['models_used'])} | {r['error'][:60]} |")
