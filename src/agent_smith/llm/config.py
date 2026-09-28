from pydantic import BaseModel, Field
from pathlib import Path


class ProviderConfig(BaseModel):
    """
    One OpenAI-compatible provider: where to send requests
    and which env vars hold its API keys
    """
    name: str = Field(..., description="Name of the provider")
    base_url: str = Field(..., description="URL of the provider")
    key_env: str = Field(..., description="Prefix of the env variable")


class ModelTarget(BaseModel):
    """
    A (provider name, model) pair, used as a fallback
    when the primary model becomes unusable
    """
    provider: str = Field(..., description="Name of the provider")
    model: str = Field(..., description="Model used by the provider")


class LLMConfig(BaseModel):
    """
    LLM client settings loaded from config/llm.json:
    providers, fallbacks and retry policy (keys stay in .env)
    """
    providers: list[ProviderConfig] = Field(
        ..., description="List of all ProviderConfig")
    fallbacks: list[ModelTarget] = Field(
        default_factory=list[ModelTarget],
        description="List of all ModelTarget")
    request_timeout_seconds: float = Field(
        default=60.0, description="Max time for one LLM request")
    max_attempts: int = Field(
        default=8, description="Max requests per complete call")
    backoff_base_seconds: float = Field(
        default=1.0,
        description="First wait before a retry, doubled each time")
    backoff_max_seconds: float = Field(
        default=20.0, description="Upper bound of a single backoff wait")

    @classmethod
    def from_file(
        cls,
        path: str | Path
    ) -> "LLMConfig":
        """
        Create a LLMConfig parsed with pydantic and returns it
        """
        text = Path(path).read_text()
        return cls.model_validate_json(text)

    def provider(
            self,
            name: str
    ) -> ProviderConfig:
        """
        Find the provider with name and returns it
        """
        for provider in self.providers:
            if provider.name == name:
                return provider
        known = ", ".join(p.name for p in self.providers)
        raise ValueError(f"No provider for name: '{name}'.\nKnown: {known}")

    def provider_for_url(
            self,
            url: str
    ) -> ProviderConfig:
        """
        Find the provider with base_url and returns it
        """
        for provider in self.providers:
            if provider.base_url.rstrip("/") == url.rstrip("/"):
                return provider
        known = ", ".join(p.base_url for p in self.providers)
        raise ValueError(f"No provider for URL: '{url}'.\nKnown: {known}")
