import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from agent_smith.llm.config import LLMConfig, ModelTarget, ProviderConfig


def make_config() -> LLMConfig:
    """
    Two providers built in code, independent of config/llm.json
    """
    return LLMConfig(providers=[
        ProviderConfig(name="groq", base_url="https://api.groq.com/openai/v1",
                       key_env="GROQ_API_KEY"),
        ProviderConfig(name="gemini", base_url="https://gemini.test/openai/",
                       key_env="GEMINI_API_KEY"),
    ])


def write_json(tmp_path: Path, data: dict[str, object]) -> Path:
    """
    Write data to a temporary JSON file and return its path
    """
    path = tmp_path / "llm.json"
    path.write_text(json.dumps(data))
    return path


# --- from_file

def test_real_config_file_loads() -> None:
    config = LLMConfig.from_file("config/llm.json")
    assert [p.name for p in config.providers] == [
        "openrouter", "groq", "gemini"]


def test_from_file_accepts_str_and_path() -> None:
    assert LLMConfig.from_file("config/llm.json") == \
        LLMConfig.from_file(Path("config/llm.json"))


def test_defaults_when_only_providers_given(tmp_path: Path) -> None:
    path = write_json(tmp_path, {"providers": [
        {"name": "groq", "base_url": "u", "key_env": "K"}]})
    config = LLMConfig.from_file(path)
    assert config.fallbacks == []
    assert config.max_attempts == 8
    assert config.request_timeout_seconds == 60.0


def test_fallbacks_are_parsed(tmp_path: Path) -> None:
    path = write_json(tmp_path, {
        "providers": [{"name": "groq", "base_url": "u", "key_env": "K"}],
        "fallbacks": [{"provider": "groq", "model": "llama"}]})
    config = LLMConfig.from_file(path)
    assert config.fallbacks == [ModelTarget(provider="groq", model="llama")]


def test_missing_providers_rejected(tmp_path: Path) -> None:
    path = write_json(tmp_path, {"max_attempts": 3})
    with pytest.raises(ValidationError):
        LLMConfig.from_file(path)


def test_missing_provider_field_rejected(tmp_path: Path) -> None:
    path = write_json(tmp_path, {"providers": [{"name": "groq"}]})
    with pytest.raises(ValidationError):
        LLMConfig.from_file(path)


def test_wrong_type_rejected(tmp_path: Path) -> None:
    path = write_json(tmp_path, {
        "providers": [{"name": "groq", "base_url": "u", "key_env": "K"}],
        "max_attempts": "eight"})
    with pytest.raises(ValidationError):
        LLMConfig.from_file(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LLMConfig.from_file(tmp_path / "nope.json")


# --- provider

def test_provider_by_name() -> None:
    assert make_config().provider("gemini").key_env == "GEMINI_API_KEY"


def test_unknown_provider_name_lists_known_names() -> None:
    with pytest.raises(ValueError) as error:
        make_config().provider("mistral")
    assert "mistral" in str(error.value)
    assert "Known: groq, gemini" in str(error.value)


# --- provider_for_url

@pytest.mark.parametrize("url", [
    "https://api.groq.com/openai/v1",
    "https://api.groq.com/openai/v1/",
])
def test_provider_for_url_ignores_trailing_slash(url: str) -> None:
    assert make_config().provider_for_url(url).name == "groq"


def test_provider_for_url_config_with_trailing_slash() -> None:
    assert make_config().provider_for_url(
        "https://gemini.test/openai").name == "gemini"


def test_unknown_url_lists_known_urls() -> None:
    with pytest.raises(ValueError) as error:
        make_config().provider_for_url("https://unknown.test/v1")
    assert "https://unknown.test/v1" in str(error.value)
    assert "https://api.groq.com/openai/v1" in str(error.value)
