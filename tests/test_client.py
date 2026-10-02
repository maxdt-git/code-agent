from typing import Any
import pytest
from agent_smith.llm.backend import ChatResult
from agent_smith.llm.client import LLMClient
from agent_smith.llm.config import LLMConfig, ModelTarget, ProviderConfig
from agent_smith.llm.errors import (
    KeyRejectedError, LLMUnavailableError, ModelUnavailableError,
    RateLimitedError, RequestRejectedError, TransientError)


GROQ_URL = "https://api.groq.com/openai/v1"
MODEL = "llama-test"
MESSAGES = [{"role": "user", "content": "hi"}]


class FakeBackend:
    """
    ChatBackend playing a script: each chat call records its arguments,
    then returns the next ChatResult or raises the next exception
    """
    def __init__(self, script: list[ChatResult | Exception]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    def chat(
            self,
            *,
            base_url: str,
            api_key: str,
            model: str,
            messages: list[dict[str, str]],
            stop: list[str] | None,
            max_tokens: int | None,
            timeout: float
    ) -> ChatResult:
        self.calls.append({
            "base_url": base_url, "api_key": api_key, "model": model,
            "messages": messages, "stop": stop, "max_tokens": max_tokens,
            "timeout": timeout})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ok() -> ChatResult:
    return ChatResult(
        text="hello", input_tokens=10, output_tokens=2, finish_reason="stop")


def make_config() -> LLMConfig:
    """
    One provider built in code, independent of config/llm.json
    """
    return LLMConfig(providers=[
        ProviderConfig(name="groq", base_url=GROQ_URL,
                       key_env="GROQ_API_KEY"),
    ])


def make_client(
        script: list[ChatResult | Exception],
        environ: dict[str, str] | None = None
) -> tuple[LLMClient, FakeBackend, list[float]]:
    """
    Client wired to a FakeBackend and a fake sleep recording its waits
    """
    backend = FakeBackend(script)
    sleeps: list[float] = []
    if environ is None:
        environ = {"GROQ_API_KEY_1": "key-one"}
    client = LLMClient(
        make_config(), GROQ_URL, MODEL,
        backend=backend, environ=environ, sleep=sleeps.append)
    return client, backend, sleeps


# --- success

def test_first_try_success() -> None:
    client, backend, sleeps = make_client([ok()])
    completion = client.complete(MESSAGES)
    assert completion.result.text == "hello"
    assert completion.retries == 0
    assert completion.requests == 1
    assert completion.api_url == GROQ_URL
    assert completion.model == MODEL
    assert sleeps == []
    assert len(backend.calls) == 1


def test_backend_receives_key_value_and_arguments() -> None:
    client, backend, _ = make_client([ok()])
    client.complete(MESSAGES, stop=["<end_code>"], max_tokens=50)
    call = backend.calls[0]
    assert call["api_key"] == "key-one"
    assert call["base_url"] == GROQ_URL
    assert call["model"] == MODEL
    assert call["messages"] == MESSAGES
    assert call["stop"] == ["<end_code>"]
    assert call["max_tokens"] == 50
    assert call["timeout"] == 60.0


def test_request_time_measures_the_backend_call() -> None:
    backend = FakeBackend([ok()])
    ticks = iter([100.0, 100.8])
    client = LLMClient(
        make_config(), GROQ_URL, MODEL, backend=backend,
        environ={"GROQ_API_KEY_1": "key-one"}, clock=lambda: next(ticks))
    completion = client.complete(MESSAGES)
    assert completion.request_time_ms == pytest.approx(800.0)


# --- transient errors

def test_transient_errors_are_retried_with_backoff() -> None:
    client, backend, sleeps = make_client(
        [TransientError("503"), TransientError("503"), ok()])
    completion = client.complete(MESSAGES)
    assert completion.retries == 2
    assert completion.requests == 3
    assert sleeps == [1.0, 2.0]
    assert len(backend.calls) == 3


def test_backoff_is_capped() -> None:
    script: list[ChatResult | Exception] = [
        TransientError("503") for _ in range(6)]
    client, _, sleeps = make_client(script + [ok()])
    client.complete(MESSAGES)
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 20.0]


def test_gives_up_after_max_attempts() -> None:
    client, backend, _ = make_client(
        [TransientError("503") for _ in range(8)])
    with pytest.raises(LLMUnavailableError) as error:
        client.complete(MESSAGES)
    assert len(backend.calls) == 8
    assert isinstance(error.value.__cause__, TransientError)


def test_no_sleep_after_last_attempt() -> None:
    client, _, sleeps = make_client(
        [TransientError("503") for _ in range(8)])
    with pytest.raises(LLMUnavailableError):
        client.complete(MESSAGES)
    assert len(sleeps) == 7


# --- errors that are not retried

def test_request_rejected_is_raised_untouched() -> None:
    client, backend, sleeps = make_client(
        [RequestRejectedError("400"), ok()])
    with pytest.raises(RequestRejectedError):
        client.complete(MESSAGES)
    assert len(backend.calls) == 1
    assert sleeps == []


def test_no_key_raises_without_calling_backend() -> None:
    client, backend, _ = make_client([ok()], environ={})
    with pytest.raises(LLMUnavailableError) as error:
        client.complete(MESSAGES)
    assert "GROQ_API_KEY" in str(error.value)
    assert backend.calls == []


# --- construction

def test_unknown_url_raises_value_error() -> None:
    with pytest.raises(ValueError):
        LLMClient(make_config(), "https://unknown.test/v1", MODEL,
                  backend=FakeBackend([]), environ={})


# --- rejected keys

TWO_KEYS = {"GROQ_API_KEY_1": "key-one", "GROQ_API_KEY_2": "key-two"}


def test_rejected_key_switches_to_next_key() -> None:
    client, backend, sleeps = make_client(
        [KeyRejectedError("401"), ok()], environ=TWO_KEYS)
    completion = client.complete(MESSAGES)
    assert backend.calls[0]["api_key"] == "key-one"
    assert backend.calls[1]["api_key"] == "key-two"
    assert completion.retries == 1
    assert sleeps == []


def test_all_keys_rejected_gives_up() -> None:
    client, backend, sleeps = make_client(
        [KeyRejectedError("401"), KeyRejectedError("401"), ok()],
        environ=TWO_KEYS)
    with pytest.raises(LLMUnavailableError) as error:
        client.complete(MESSAGES)
    assert len(backend.calls) == 2
    assert isinstance(error.value.__cause__, KeyRejectedError)
    assert sleeps == []


def test_rejected_key_stays_disabled_between_calls() -> None:
    client, backend, _ = make_client(
        [KeyRejectedError("401"), ok(), ok()], environ=TWO_KEYS)
    client.complete(MESSAGES)
    completion = client.complete(MESSAGES)
    assert backend.calls[2]["api_key"] == "key-two"
    assert completion.retries == 0
    assert completion.requests == 1


# --- rate limits

def test_rate_limit_rotates_without_waiting() -> None:
    client, backend, sleeps = make_client(
        [RateLimitedError("429"), ok()], environ=TWO_KEYS)
    completion = client.complete(MESSAGES)
    assert backend.calls[1]["api_key"] == "key-two"
    assert completion.retries == 1
    assert sleeps == []


def test_waits_once_when_every_key_is_limited() -> None:
    script: list[ChatResult | Exception] = [
        RateLimitedError("429") for _ in range(3)]
    client, backend, sleeps = make_client(script + [ok()], environ={
        "GROQ_API_KEY_1": "key-one", "GROQ_API_KEY_2": "key-two",
        "GROQ_API_KEY_3": "key-three"})
    completion = client.complete(MESSAGES)
    assert [call["api_key"] for call in backend.calls] == [
        "key-one", "key-two", "key-three", "key-one"]
    assert sleeps == [1.0]
    assert completion.retries == 3


def test_rate_limit_wait_uses_retry_after() -> None:
    client, _, sleeps = make_client(
        [RateLimitedError("429", retry_after=5.0), ok()])
    client.complete(MESSAGES)
    assert sleeps == [5.0]


def test_retry_after_is_capped() -> None:
    client, _, sleeps = make_client(
        [RateLimitedError("429", retry_after=3600.0), ok()])
    client.complete(MESSAGES)
    assert sleeps == [20.0]


def test_rate_limit_no_sleep_after_last_attempt() -> None:
    client, backend, sleeps = make_client(
        [RateLimitedError("429") for _ in range(8)])
    with pytest.raises(LLMUnavailableError) as error:
        client.complete(MESSAGES)
    assert len(backend.calls) == 8
    assert len(sleeps) == 7
    assert isinstance(error.value.__cause__, RateLimitedError)


def test_rate_limit_skips_rejected_key() -> None:
    client, backend, sleeps = make_client(
        [KeyRejectedError("401"), RateLimitedError("429"), ok()],
        environ=TWO_KEYS)
    client.complete(MESSAGES)
    assert [call["api_key"] for call in backend.calls] == [
        "key-one", "key-two", "key-two"]
    assert sleeps == [1.0]


# --- fallbacks

GEMINI_URL = "https://gemini.test/openai"
FALLBACK_MODEL = "gemini-test"
BOTH_PROVIDERS = {"GROQ_API_KEY_1": "groq-one", "GEMINI_API_KEY_1": "gem-one"}


def make_fallback_client(
        script: list[ChatResult | Exception],
        environ: dict[str, str]
) -> tuple[LLMClient, FakeBackend, list[float]]:
    """
    Client whose primary target is groq, with gemini as fallback
    """
    config = LLMConfig(
        providers=[
            ProviderConfig(name="groq", base_url=GROQ_URL,
                           key_env="GROQ_API_KEY"),
            ProviderConfig(name="gemini", base_url=GEMINI_URL,
                           key_env="GEMINI_API_KEY"),
        ],
        fallbacks=[ModelTarget(provider="gemini", model=FALLBACK_MODEL)])
    backend = FakeBackend(script)
    sleeps: list[float] = []
    client = LLMClient(
        config, GROQ_URL, MODEL,
        backend=backend, environ=environ, sleep=sleeps.append)
    return client, backend, sleeps


def test_model_unavailable_switches_to_fallback() -> None:
    client, backend, sleeps = make_fallback_client(
        [ModelUnavailableError("404"), ok()], BOTH_PROVIDERS)
    completion = client.complete(MESSAGES)
    assert backend.calls[0]["base_url"] == GROQ_URL
    assert backend.calls[1]["base_url"] == GEMINI_URL
    assert backend.calls[1]["model"] == FALLBACK_MODEL
    assert backend.calls[1]["api_key"] == "gem-one"
    assert completion.api_url == GEMINI_URL
    assert completion.model == FALLBACK_MODEL
    assert completion.retries == 1
    assert sleeps == []


def test_fallback_is_kept_for_next_calls() -> None:
    client, backend, _ = make_fallback_client(
        [ModelUnavailableError("404"), ok(), ok()], BOTH_PROVIDERS)
    client.complete(MESSAGES)
    completion = client.complete(MESSAGES)
    assert backend.calls[2]["base_url"] == GEMINI_URL
    assert completion.retries == 0


def test_no_key_for_primary_goes_straight_to_fallback() -> None:
    client, backend, _ = make_fallback_client(
        [ok()], {"GEMINI_API_KEY_1": "gem-one"})
    completion = client.complete(MESSAGES)
    assert len(backend.calls) == 1
    assert backend.calls[0]["base_url"] == GEMINI_URL
    assert completion.retries == 0
    assert completion.requests == 1


def test_rejected_keys_exhausted_switches_to_fallback() -> None:
    client, backend, _ = make_fallback_client(
        [KeyRejectedError("401"), ok()], BOTH_PROVIDERS)
    completion = client.complete(MESSAGES)
    assert backend.calls[1]["base_url"] == GEMINI_URL
    assert completion.api_url == GEMINI_URL
    assert completion.retries == 1


def test_all_targets_unavailable_gives_up() -> None:
    client, backend, _ = make_fallback_client(
        [ModelUnavailableError("404"), ModelUnavailableError("404"), ok()],
        BOTH_PROVIDERS)
    with pytest.raises(LLMUnavailableError) as error:
        client.complete(MESSAGES)
    assert len(backend.calls) == 2
    assert isinstance(error.value.__cause__, ModelUnavailableError)


def test_no_key_anywhere_names_the_missing_key() -> None:
    client, backend, _ = make_fallback_client([ok()], {})
    with pytest.raises(LLMUnavailableError) as error:
        client.complete(MESSAGES)
    assert "GROQ_API_KEY" in str(error.value)
    assert backend.calls == []


def test_model_unavailable_without_fallback_gives_up() -> None:
    client, backend, _ = make_client([ModelUnavailableError("404"), ok()])
    with pytest.raises(LLMUnavailableError):
        client.complete(MESSAGES)
    assert len(backend.calls) == 1
