from collections.abc import Callable, Mapping
from dataclasses import dataclass
from agent_smith.llm.backend import \
    (ChatResult, ChatBackend, OpenAICompatBackend)
from agent_smith.llm.config import LLMConfig, ModelTarget
import time
from agent_smith.llm.keys import KeyPool


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

        self._pools: dict[str, KeyPool] = {}
        for target in self._targets:
            if target.provider not in self._pools:
                key = config.provider(target.provider)
                self._pools[key.name] = KeyPool(key.key_env, environ)

        self._target_index: int = 0
