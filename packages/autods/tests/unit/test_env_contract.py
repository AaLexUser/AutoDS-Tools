from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from autods.utils.llm_client import LLMClient


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTODS_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("AUTODS_API_KEY", "test-api-key")
    monkeypatch.setenv("AUTODS_BASE_URL", "https://gateway.example.com/v1")


def _install_fake_chat_openai(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))
    return captured


def test_llm_client_reads_openai_compatible_settings_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AUTODS_MAX_RETRIES", "7")
    monkeypatch.setenv("AUTODS_MODEL_KWARGS_JSON", '{"temperature": 0.2}')
    monkeypatch.setenv("AUTODS_EXTRA_BODY_JSON", '{"reasoning": {"effort": "medium"}}')
    monkeypatch.setenv("AUTODS_DEFAULT_HEADERS_JSON", '{"X-Test": "1"}')
    captured = _install_fake_chat_openai(monkeypatch)

    client = LLMClient()

    assert client is not None
    assert captured == {
        "model": "gpt-4.1-mini",
        "api_key": "test-api-key",
        "base_url": "https://gateway.example.com/v1",
        "max_retries": 7,
        "model_kwargs": {"temperature": 0.2},
        "extra_body": {"reasoning": {"effort": "medium"}},
        "default_headers": {"X-Test": "1"},
    }


@pytest.mark.parametrize(
    "missing_var",
    [
        "AUTODS_MODEL",
        "AUTODS_API_KEY",
        "AUTODS_BASE_URL",
    ],
)
def test_llm_client_fails_fast_for_missing_required_env(
    monkeypatch: pytest.MonkeyPatch,
    missing_var: str,
) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.delenv(missing_var, raising=False)
    _install_fake_chat_openai(monkeypatch)

    with pytest.raises(ValueError, match=missing_var):
        LLMClient()


@pytest.mark.parametrize(
    ("env_name", "value"),
    [
        ("AUTODS_MODEL_KWARGS_JSON", "{not-json}"),
        ("AUTODS_EXTRA_BODY_JSON", '{"broken"'),
        ("AUTODS_DEFAULT_HEADERS_JSON", "[1, 2, 3]"),
    ],
)
def test_llm_client_rejects_invalid_json_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    value: str,
) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv(env_name, value)
    _install_fake_chat_openai(monkeypatch)

    with pytest.raises(ValueError, match=env_name):
        LLMClient()
