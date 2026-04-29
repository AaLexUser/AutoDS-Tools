import json
import os
from typing import Any, cast


def _required_env(name: str, override: str | None = None) -> str:
    value = override if override is not None else os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"{name} environment variable is required")
    return value


def _optional_int_env(name: str, default: int, override: int | None = None) -> int:
    if override is not None:
        return override
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_json_dict_env(
    name: str,
    override: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if override is not None:
        return override
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} contains invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must decode to a JSON object")
    return value


class LLMClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int | None = None,
        model_kwargs: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
        default_headers: dict[str, Any] | None = None,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self._client = ChatOpenAI(
            model=_required_env("AUTODS_MODEL", model),
            api_key=cast(Any, _required_env("AUTODS_API_KEY", api_key)),
            base_url=_required_env("AUTODS_BASE_URL", base_url),
            max_retries=_optional_int_env("AUTODS_MAX_RETRIES", 3, max_retries),
            model_kwargs=_optional_json_dict_env("AUTODS_MODEL_KWARGS_JSON", model_kwargs) or {},
            extra_body=_optional_json_dict_env("AUTODS_EXTRA_BODY_JSON", extra_body),
            default_headers=_optional_json_dict_env("AUTODS_DEFAULT_HEADERS_JSON", default_headers),
        )

    async def ainvoke(self, input: Any, **kwargs: Any) -> Any:
        return await self._client.ainvoke(input, **kwargs)
