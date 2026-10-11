"""Environment-only configuration for demo and guarded live adapters."""
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.providers.search_safety import normalize_domains


DomainTuple = Annotated[tuple[str, ...], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, frozen=True, extra='ignore')
    app_mode: Literal['demo', 'live'] = 'demo'
    enable_live_workflow: bool = False
    database_url: str = 'sqlite:///veriplan.db'
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = 'deepseek-v4-flash'
    deepseek_timeout_seconds: int = Field(default=30, ge=1, le=120)
    deepseek_max_output_tokens: int = Field(default=4096, ge=512, le=8192)
    tavily_api_key: SecretStr | None = None
    tavily_timeout_seconds: int = Field(default=15, ge=1, le=30)
    tavily_trusted_domains: DomainTuple = ()
    tavily_blocked_domains: DomainTuple = ()

    @field_validator(
        "tavily_trusted_domains",
        "tavily_blocked_domains",
        mode="before",
    )
    @classmethod
    def parse_domain_list(cls, value):
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(value.split(","))
        if isinstance(value, (list, tuple)):
            return tuple(value)
        raise ValueError("domain configuration must be comma-separated text")

    @field_validator("tavily_trusted_domains", "tavily_blocked_domains")
    @classmethod
    def validate_domains(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return normalize_domains(value)
