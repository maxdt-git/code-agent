from collections.abc import Callable, Mapping
from dataclasses import dataclass
from agent_smith.llm.backend import \
    (ChatResult, ChatBackend, OpenAICompatBackend)
from agent_smith.llm.config import LLMConfig, ModelTarget
import time
from agent_smith.llm.keys import KeyPool
from agent_smith.llm.errors import (
    LLMUnavailableError, TransientError, LLMError, KeyRejectedError,
    RateLimitedError, ModelUnavailableError)


@dataclass
class Completion:
    """
    Result with also the nb of retries, request_time and the requests,
    api_url and model used
    """
    result: ChatResult
    request_time_ms: float
    retries: int
    requests: int
    api_url: str
    model: str


class LLMClient:
    """
    Send chat requests through a ChatBackend, retrying on failure
    and tracking requests, retries and latency for the agent metrics
    """
    def __init__(
            self,
            config: LLMConfig,
            base_url: str,
            model: str,
            backend: ChatBackend | None = None,
            environ: Mapping[str, str] | None = None,
            sleep: Callable[[float], None] = time.sleep,
            clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._config = config
        self._sleep = sleep
        self._clock = clock
        self._backend = backend if backend is not None \
            else OpenAICompatBackend()

        self._targets: list[ModelTarget] = []
        provider = config.provider_for_url(base_url).name
        self._targets.append(ModelTarget(provider=provider, model=model))
        self._targets.extend(config.fallbacks)

        self._pools: dict[str, KeyPool] = {}
        for target in self._targets:
            if target.provider not in self._pools:
                key = config.provider(target.provider)
                self._pools[key.name] = KeyPool(key.key_env, environ)

        self._target_index: int = 0

    def backoff(self, waits: int) -> float:
        """
        returns the min between config.back_off_max_second and the time
        it should take depending on the rate limite and transient error
        """
        return float(min(
            self._config.backoff_base_seconds * 2 ** waits,
            self._config.backoff_max_seconds))

    def find_deadline(self, deadline: float | None) -> float | None:
        """
        Use to know how much time we have before the deadline
        """
        if deadline is None:
            return None
        return deadline - self._clock()

    def wait(
            self,
            seconds: float,
            deadline: float,
            last_error: LLMError | None
    ) -> None:
        ...
# Avant chaque sleep (transitoire et 429) : si l'attente prévue est supérieure
# ou égale au temps restant, ne dors pas et lève LLMUnavailableError tout de
# suite. Dormir pour se réveiller après l'heure limite ne sert à rien.
# Comme cette vérification se fait à deux endroits, mets-la dans une méthode
# privée (par exemple _wait(seconds, deadline, last_error)) qui vérifie puis
# dort. Tes deux branches except l'appelleront.

    def complete(
            self,
            messages: list[dict[str, str]],
            stop: list[str] | None = None,
            max_tokens: int | None = None,
            deadline: float | None = None
    ) -> Completion:
        """
        Returns a completion if the chat complete, else raise error
        """
        requests = 0
        waits = 0
        last_error: LLMError | None = None
        limited_in_row = 0

        while requests < self._config.max_attempts:
            if self._target_index >= len(self._targets):
                raise LLMUnavailableError(
                    f"no usable target left: {last_error}") from last_error
            available_time = self.find_deadline(deadline)
            if available_time is None or available_time <= 0:
                raise LLMUnavailableError(
                    f"deadline reached: {last_error}") from last_error
            target = self._targets[self._target_index]
            provider = self._config.provider(target.provider)
            base_url = provider.base_url
            pool = self._pools[target.provider]
            key = pool.current()

            if key is None:
                if last_error is None:
                    last_error = LLMUnavailableError(
                        f"no usable api key for {provider.key_env}")
                self._target_index += 1
                limited_in_row = 0
                continue

            requests += 1
            start = self._clock()

            try:
                chat_result = self._backend.chat(
                    base_url=base_url,
                    api_key=key[1],
                    model=target.model,
                    messages=messages,
                    stop=stop,
                    max_tokens=max_tokens,
                    timeout=min(
                        available_time, self._config.request_timeout_seconds))
                request_time_ms = (self._clock() - start) * 1000
                return Completion(
                    chat_result,
                    request_time_ms,
                    requests - 1,
                    requests,
                    base_url,
                    target.model)

            except TransientError as e:
                last_error = e
                if requests < self._config.max_attempts:
                    self._sleep(self.backoff(waits))
                    waits += 1

            except KeyRejectedError as e:
                last_error = e
                pool.disable_current()

            except RateLimitedError as e:
                last_error = e
                pool.rotate()
                limited_in_row += 1
                if limited_in_row >= pool.live_count:
                    limited_in_row = 0
                    if requests < self._config.max_attempts:
                        wait_sec = e.retry_after if e.retry_after is not None \
                            else self.backoff(waits)
                        wait_sec = min(
                            wait_sec, self._config.backoff_max_seconds)
                        self._sleep(wait_sec)
                        waits += 1

            except ModelUnavailableError as e:
                last_error = e
                self._target_index += 1
                limited_in_row = 0

        raise LLMUnavailableError(
            f"gave up after {requests} requests {last_error}") from last_error
