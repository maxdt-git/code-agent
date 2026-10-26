from agent_smith.sandbox.executor import ExecutionResult
from agent_smith.agent.extract import Extraction, extract_code
from agent_smith.models import StepMetrics
from agent_smith.sandbox.sandbox import Sandbox
from dataclasses import dataclass
from agent_smith.llm.client import LLMClient
from agent_smith.llm.errors import LLMError


def format_observation(
        extraction: Extraction,
        result: ExecutionResult | None
) -> str:
    """
    Build note for the llm
    """
    parts: list[str] = []
    if extraction.note:
        parts.append(
            f"Note: {extraction.note}")
    if result is None:
        return "Observation:\n" + "\n".join(parts)
    # partial output
    if result.timed_out:
        parts.append("Execution timed out: the output below is partial.")
    parts.append(
        "Output:\n" + (
            result.output or "nothing was printed, use print() to see values"))
    if result.error:
        parts.append("Error:\n" + result.error)
    return "Observation:\n" + "\n".join(parts)


@dataclass
class AgentRun:
    """
    What happened during the loop: answer (or None), steps, error
    """
    answer: str | None
    steps: list[StepMetrics]
    error: str | None


STOP = ["<end_code>"]
MAX_TOKENS_PER_STEP = 600
BUDGET_MARGIN = 0.90


def run_agent(
        client: LLMClient,
        sandbox: Sandbox,
        system_prompt: str,
        task_prompt: str,
        max_iterations: int,
        deadline: float,
        max_input_tokens: int,
        max_output_tokens: int
) -> AgentRun:
    """
    Run the agent and returns an AgentRun
    """
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt}]

    steps: list[StepMetrics] = []
    used_input = 0
    used_output = 0
    try:
        for step in range(1, max_iterations + 1):
            # caclulate how much token this step cost at most
            next_input = sum(len(m["content"]) for m in messages) // 4
            max_tokens = min(
                MAX_TOKENS_PER_STEP, max_output_tokens - used_output)
            if (used_input + next_input > max_input_tokens * BUDGET_MARGIN
                    or max_tokens < 100):
                return AgentRun(None, steps, "token budget reached")

            completion = client.complete(
                messages, STOP, max_tokens=max_tokens, deadline=deadline)
            text = completion.result.text
            extraction = extract_code(text)
            result = sandbox.execute(extraction.code) \
                if extraction.code else None
            observation = format_observation(extraction, result)

            # real cost of this step, added to the totals
            input_tokens = completion.result.input_tokens or next_input
            output_tokens = completion.result.output_tokens or len(text) // 4
            used_input += input_tokens
            used_output += output_tokens

            steps.append(StepMetrics(
                step=step,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_time_ms=completion.request_time_ms,
                api_url=completion.api_url,
                model_name=completion.model,
                retries=completion.retries,
                llm_output=text,
                sandbox_input=extraction.code or "",
                sandbox_output=observation
            ))

            if result and result.final_answer is not None:
                return AgentRun(result.final_answer, steps, None)
            messages.append(
                {"role": "assistant", "content": text + "<end_code>"})
            messages.append({"role": "user", "content": observation})
    except LLMError as e:
        return AgentRun(None, steps, f"LLM unavailable: {e}")
    return AgentRun(None, steps, f"no final_answer after {max_iterations}")


# if __name__ == "__main__":
#     print(format_observation(
#         Extraction("x"), ExecutionResult("4\n", None, None)))
#     print(format_observation(
#         Extraction("x"), ExecutionResult("", None, None)))
#     print(format_observation(
#         Extraction(None, "No code found..."), None))
