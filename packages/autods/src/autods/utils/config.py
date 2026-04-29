import os
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from autods.constants import (
    AUTO_DS_AGENT,
    DEFAULT_CONFIG_PATH,
)


class ConfigError(Exception):
    pass


class ModelProvider(BaseModel):
    """
    Model provider configuration. For official model providers such as OpenAI and Anthropic,
    the base_url is optional. api_version is required for Azure.
    """

    api_key: str
    provider: str
    base_url: str | None = None


class ModelConfig(BaseModel):
    """
    Model configuration.
    """

    model: str
    model_provider: ModelProvider
    max_retries: int
    model_kwargs: dict[str, Any] | None = None
    extra_body: dict[str, Any] | None = None
    default_headers: dict[str, str] | None = None

    def resolve_config_values(
        self,
        *,
        model_providers: dict[str, ModelProvider] | None = None,
        provider: str | None = None,
        model: str | None = None,
        model_base_url: str | None = None,
        api_key: str | None = None,
    ):
        """
        When some config values are provided through CLI or environment variables,
        they will override the values in the config file.
        """
        self.model = str(resolve_config_value(cli_value=model, config_value=self.model))

        # If the user wants to change the model provider, they should either:
        # * Make sure the provider name is available in the model_providers dict;
        # * If not, base url and api key should be provided to register a new model provider.
        if provider:
            if model_providers and provider in model_providers:
                self.model_provider = model_providers[provider]
            elif api_key is None:
                raise ConfigError("To register a new model provider, an api_key should be provided")
            else:
                self.model_provider = ModelProvider(
                    api_key=api_key,
                    provider=provider,
                    base_url=model_base_url,
                )

        # Map providers to their environment variable names
        env_var_api_key = str(self.model_provider.provider).upper() + "_API_KEY"
        env_var_api_base_url = str(self.model_provider.provider).upper() + "_BASE_URL"

        resolved_api_key = resolve_config_value(
            cli_value=api_key,
            config_value=self.model_provider.api_key,
            env_var=env_var_api_key,
        )

        resolved_api_base_url = resolve_config_value(
            cli_value=model_base_url,
            config_value=self.model_provider.base_url,
            env_var=env_var_api_base_url,
        )

        if resolved_api_key:
            self.model_provider.api_key = str(resolved_api_key)

        if resolved_api_base_url:
            self.model_provider.base_url = str(resolved_api_base_url)


class AgentConfig(BaseModel):
    """
    Base class for agent configurations.
    """

    name: str | None = None
    model: ModelConfig
    max_steps: int = Field(default=50)

    @classmethod
    def from_dict(cls, agent_name: str, data: dict, config: "Config") -> "AgentConfig":
        agent_cfg_dict: dict = {**data}
        agent_cfg_dict["name"] = agent_name

        # Resolve Allowed MCP server configs
        mcp_servers_config = {}
        allowed_servers = agent_cfg_dict.get("allow_mcp_servers", [])
        if not isinstance(allowed_servers, list):
            raise ConfigError(f"allow_mcp_servers for agent '{agent_name}' must be a list")

        for server in allowed_servers:
            server_cfg = config.mcp_servers.get(server)
            if server_cfg is None:
                raise ConfigError(
                    f"MCP server '{server}' is allowed for agent '{agent_name}' but not defined under 'mcp_servers'"
                )
            mcp_servers_config[server] = server_cfg

        agent_cfg_dict["mcp_servers_config"] = mcp_servers_config
        agent_cfg_dict["allow_mcp_servers"] = allowed_servers

        # Resolve model reference
        model_name = agent_cfg_dict.get("model")
        if not isinstance(model_name, str):
            raise ConfigError(f"Model reference for agent '{agent_name}' must be a string")

        try:
            agent_cfg_dict["model"] = Config.resolve_model_reference(config=config, model_name=model_name)
        except ConfigError as exc:
            raise ConfigError(f"Model '{model_name}' referenced by agent '{agent_name}' is not defined") from exc
        # Choose specialized config class for well-known agents
        config_cls: type[AgentConfig] = cls
        if agent_name == AUTO_DS_AGENT:
            config_cls = AutoDSAgentConfig

        return config_cls.model_validate(agent_cfg_dict)


class AutoDSAgentConfig(AgentConfig):
    """
    Config for the AutoDS agent.
    """

    analyst_steps: int = Field(default=0)
    researcher_steps: int = Field(default=0)
    planner_steps: int = Field(default=0)
    debugger_steps: int = Field(default=0)
    presenter_steps: int = Field(default=5)


class Config(BaseModel):
    """
    Configuration class for agents, models and model providers.
    """

    model_providers: dict[str, ModelProvider] = Field(default_factory=dict)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Selected default model configuration (resolved at load time). Optional for typing.
    model: ModelConfig | None = None
    agents: dict[str, AgentConfig] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        config_file: str | None = None,
        config_string: str | None = None,
    ) -> "Config":
        if config_file and config_string:
            raise ConfigError("Only one of config_file or config_string should be provided")

        # Parse YAML config from file or string
        try:
            if config_file is not None:
                with open(config_file, "r") as f:
                    yaml_config = yaml.safe_load(f)
            elif config_string is not None:
                yaml_config = yaml.safe_load(config_string)
            else:
                raise ConfigError("No config file or config string provided")
        except yaml.YAMLError as e:
            raise ConfigError(f"Error parsing YAML config: {e}") from e

        # Resolve all environment variable substitutions in the entire config
        yaml_config = resolve_env_variables(yaml_config)

        config = cls()

        # ====== ENV ========
        envvar = yaml_config.get("env", None)
        if envvar is not None and isinstance(envvar, dict) and len(envvar.keys()) > 0:
            for key, val in envvar.items():
                if val is not None:
                    os.environ[key] = val

        # ======= Model Providers =======
        model_providers = yaml_config.get("model_providers", None)
        if model_providers is not None and len(model_providers.keys()) > 0:
            config_model_providers: dict[str, ModelProvider] = {}
            for model_provider_name, model_provider_config in model_providers.items():
                config_model_providers[model_provider_name] = ModelProvider.model_validate(model_provider_config)
            config.model_providers = config_model_providers
        else:
            raise ConfigError("No model providers provided")

        # ======= Models =======
        models = yaml_config.get("models", None)
        if models is not None and len(models.keys()) > 0:
            config_models: dict[str, ModelConfig] = {}
            for model_name, model_config in models.items():
                model_provider_ref = model_config.get("model_provider", None)
                if model_provider_ref is None:
                    raise ConfigError(f"Model provider not specified for model: {model_name}")
                model_provider = config.model_providers.get(model_provider_ref, None)
                if model_provider is None:
                    raise ConfigError(
                        f"Model provider {model_provider_ref} for model {model_name} is not defined in model_providers"
                    )
                model_config["model_provider"] = model_provider
                config_models[model_name] = ModelConfig.model_validate(model_config)
            config.models = config_models
        else:
            raise ConfigError("No models provided")

        # ======= MCP Servers =======
        mcp_servers = yaml_config.get("mcp_servers", None)
        if mcp_servers is not None:
            if not isinstance(mcp_servers, dict):
                raise ConfigError("mcp_servers must be a mapping when provided")
            config.mcp_servers = {
                str(server_name): server_config
                for server_name, server_config in mcp_servers.items()
                if isinstance(server_config, dict)
            }

        # ====== Agents =======
        agents = yaml_config.get("agents", None)
        agent_configs: dict[str, AgentConfig] = {}
        if agents is not None and len(agents.keys()) > 0:
            for agent_name, agent_config in agents.items():
                agent_configs[agent_name] = AgentConfig.from_dict(agent_name, agent_config, config)
            config.agents = agent_configs
        else:
            raise ConfigError("No agent configs provided")
        return config

    def resolve_config_values(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        model_base_url: str | None = None,
        api_key: str | None = None,
        max_steps: int | None = None,
    ):
        autods_agent = self.agents.get("autods")
        if autods_agent:
            if max_steps is not None:
                autods_agent.max_steps = max_steps

            autods_agent.model.resolve_config_values(
                model_providers=self.model_providers,
                provider=provider,
                model=model,
                model_base_url=model_base_url,
                api_key=api_key,
            )
        return self

    @staticmethod
    def resolve_model_reference(config: "Config", model_name: str) -> ModelConfig:
        if isinstance(model_name, str):
            if model_name not in config.models:
                raise ConfigError(f"Model '{model_name}' referenced is not defined")
            return config.models[model_name]


def resolve_env_variables(value):
    """
    Recursively resolve environment variable substitutions in configuration values.

    Args:
        value: The value to process (can be dict, list, str, or other types)

    Returns:
        The value with environment variables resolved
    """
    if isinstance(value, dict):
        return {key: resolve_env_variables(val) for key, val in value.items()}
    elif isinstance(value, list):
        return [resolve_env_variables(item) for item in value]
    elif isinstance(value, str):
        # Handle environment variable substitution: ${VAR_NAME}
        if value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]  # Remove ${ and }
            return os.getenv(env_var, value)  # Return original if env var not found
        return value
    else:
        return value


def resolve_config_value(
    *,
    cli_value: int | str | float | None,
    config_value: int | str | float | None,
    env_var: str | None = None,
) -> int | str | float | None:
    """Resolve configuration value with priority: CLI > ENV > Config > Default."""
    if cli_value is not None:
        return cli_value

    if env_var and os.getenv(env_var):
        return os.getenv(env_var)

    if config_value is not None:
        return config_value

    return None


def load_config(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    model_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_steps: Optional[int] = None,
    config_file: Optional[str] = None,
) -> Config:
    config_file = str(
        resolve_config_value(
            cli_value=config_file,
            config_value=str(DEFAULT_CONFIG_PATH),
            env_var="AUTODS_CONFIG_PATH",
        )
    )
    config = Config.create(config_file=config_file)
    config = config.resolve_config_values(
        provider=provider,
        model=model,
        model_base_url=model_base_url,
        api_key=api_key,
        max_steps=max_steps,
    )
    return config
