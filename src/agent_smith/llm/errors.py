class LLMError(Exception):
    """
    Base class for every LLM-layer error
    """


class KeyRejectedError(LLMError):
    """
    Invalid, revoked or out-of-credit key (401/402/403):
    the key is disabled, next key without waiting
    """


class RateLimitedError(LLMError):
    """
    Rate limit or quota reached (429): rotate to the next key,
    wait retry_after once every key is limited
    """
    def __init__(
            self,
            message: str,
            retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TransientError(LLMError):
    """
    Timeout, network error or server error (5xx):
    wait then retry the same request
    """


class ModelUnavailableError(LLMError):
    """
    The provider does not serve this model (404):
    switch to a fallback target, waiting or new key won't help
    """


class RequestRejectedError(LLMError):
    """
    Invalid request (400/422), too many tokens:
    retrying cannot succeed, the error is raised to the caller
    """


class LLMUnavailableError(LLMError):
    """
    Raised by the client when it gives up (no key, no attempt or no time
    left): the agent catches it to end cleanly
    """
