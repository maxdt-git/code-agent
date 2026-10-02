from dataclasses import dataclass
from typing import Protocol, Any, cast
from agent_smith.llm.errors import (
    KeyRejectedError, LLMError, ModelUnavailableError,
    RateLimitedError, RequestRejectedError, TransientError)
import openai
from openai import OpenAI, omit


# pydantic validate data from outside
# dataclass takes data from inside (data we created)
@dataclass
class ChatResult():
    """
    One successfull llm answer, token are None if not reported
    """
    text: str
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str


class ChatBackend(Protocol):
    """
    Anything that can send a chat request and returns a ChatResult
    """
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
        ...


def translate_status(
        status: int,
        message: str,
        retry_after: float | None
) -> LLMError:
    """
    Return the LLMError matching hhtp status
    """
    text = f"HTTP {status}: {message}"
    if status in (401, 402, 403):
        return KeyRejectedError(text)
    if status == 404:
        return ModelUnavailableError(text)
    if status == 408:
        return TransientError(text)
    if status == 429:
        return RateLimitedError(text, retry_after=retry_after)
    if status >= 500:
        return TransientError(text)
    return RequestRejectedError(text)


def parse_retry_after(value: str | None) -> float | None:
    """
    Parse only the retry after, need to be a float
    """
    if value is None:
        return None
    try:
        float(value)
    except ValueError:
        return None

    return float(value)


class OpenAICompatBackend:
    """
    ChatBackend for any OpenAI-compatible API (OpenRouter, Groq, Gemini),
    translating SDK errors into LLMError subclasses
    """
    def __init__(self) -> None:
        self._clients: dict[tuple[str, str], OpenAI] = {}

    def _client(
            self,
            base_url: str,
            api_key: str,
            timeout: float
    ) -> OpenAI:
        """
        If the client already in returns it, else create it and returns it
        """
        key = (base_url, api_key)
        if key in self._clients:
            return self._clients[key]
        client = OpenAI(
            base_url=base_url, api_key=api_key, max_retries=0, timeout=timeout)
        self._clients[key] = client
        return client

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
        """
        Send one request (no retry) and return the answer or raise an error
        """
        client = self._client(base_url, api_key, timeout)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=cast(Any, messages),
                stop=stop if stop else omit,
                max_tokens=max_tokens if max_tokens is not None else omit,
                timeout=timeout
            )
        except openai.APIConnectionError as e:
            raise TransientError(f"connection error: {e}") from e
        except openai.APIStatusError as e:
            message = e.message.replace(api_key, "**")
            retry_after = parse_retry_after(
                e.response.headers.get("retry-after"))
            raise translate_status(
                e.status_code, message, retry_after) from e

        if not response.choices:
            raise TransientError("empty response (no choice)")
        choice = response.choices[0]
        usage = response.usage
        return ChatResult(
            text=choice.message.content
            if choice.message.content is not None else "",
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            finish_reason=choice.finish_reason if choice.finish_reason else ""
        )
