"""Environment-driven configuration.

All configuration arrives from the environment; nothing is hardcoded per
deployment and no secret is ever committed. Values are validated at startup so
a misconfigured service fails immediately and loudly instead of failing on the
first request.

Naming convention: ``CYBERAI_<SECTION>__<FIELD>``, e.g. ``CYBERAI_DATABASE__URL``.
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyberai.core.errors import ConfigurationError

_CREDENTIALS_IN_URL = re.compile(r"://([^:/@]+):([^@]+)@")

# Values that are acceptable for local development but must never reach a
# deployed environment.
_INSECURE_DEFAULTS = frozenset({"cyberai_dev_password", "changeme", "postgres", "password"})
_DEV_AUTH_JWT_SECRET = "cyberai_dev_" + "jwt_secret_do_not_use_in_prod"


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_deployed(self) -> bool:
        return self in {Environment.STAGING, Environment.PRODUCTION}


def mask_credentials(url: str) -> str:
    """Replace the password in a connection URL so it is safe to log."""
    return _CREDENTIALS_IN_URL.sub(r"://\1:***@", url)


def _database_uses_insecure_default(url: str) -> bool:
    parsed = urlsplit(url)
    credentials = [parsed.username or "", parsed.password or ""]
    return any(value in _INSECURE_DEFAULTS for value in credentials)


class AppSettings(BaseModel):
    name: str = "cyberai-api"
    root_path: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    expose_docs: bool | None = None
    max_request_body_bytes: Annotated[int, Field(gt=0)] = 1_048_576
    # Hard ceiling for a single HTTP request, independent of inference timeouts.
    request_timeout_seconds: Annotated[float, Field(gt=0)] = 120.0


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["console", "json"] = "json"
    # Access logs for these paths are dropped; health probes would otherwise
    # bury every meaningful log line.
    silent_paths: list[str] = Field(default_factory=lambda: ["/healthz", "/readyz", "/metrics"])


class AuthSettings(BaseModel):
    jwt_secret: str = _DEV_AUTH_JWT_SECRET
    legacy_bearer_enabled: bool = True
    oidc_enabled: bool = False
    oidc_auto_provision_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str | None = None
    oidc_scope: str = "openid email profile"
    session_cookie_name: str = "cyberai_session"
    csrf_header_name: str = "X-CSRF-Token"
    session_ttl_seconds: Annotated[int, Field(gt=0)] = 28_800
    session_secure_cookie: bool | None = None
    session_samesite: Literal["lax", "strict", "none"] = "lax"
    session_secret: SecretStr | None = None
    csrf_secret: SecretStr | None = None


class DatabaseSettings(BaseModel):
    url: str = "postgresql+asyncpg://cyberai:cyberai_dev_password@localhost:5432/cyberai"
    pool_size: Annotated[int, Field(ge=1, le=100)] = 10
    max_overflow: Annotated[int, Field(ge=0, le=100)] = 5
    pool_timeout_seconds: Annotated[float, Field(gt=0)] = 30.0
    pool_recycle_seconds: Annotated[int, Field(gt=0)] = 1800
    statement_timeout_ms: Annotated[int, Field(gt=0)] = 15_000
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "database URL must use the asyncpg driver "
                "(postgresql+asyncpg://user:pass@host:port/db)"
            )
        return value

    @property
    def masked_url(self) -> str:
        return mask_credentials(self.url)


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"
    max_connections: Annotated[int, Field(ge=1, le=1000)] = 20
    socket_timeout_seconds: Annotated[float, Field(gt=0)] = 2.0
    socket_connect_timeout_seconds: Annotated[float, Field(gt=0)] = 2.0

    @field_validator("url")
    @classmethod
    def _require_redis_scheme(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("redis URL must start with redis://, rediss:// or unix://")
        return value

    @property
    def masked_url(self) -> str:
        return mask_credentials(self.url)


class InferenceSettings(BaseModel):
    """Transport-level policy for the Inference Gateway (the *how*)."""

    request_timeout_seconds: Annotated[float, Field(gt=0)] = 60.0
    first_token_timeout_seconds: Annotated[float, Field(gt=0)] = 20.0
    max_concurrent_requests_per_provider: Annotated[int, Field(ge=1, le=1024)] = 8
    circuit_breaker_failure_threshold: Annotated[int, Field(ge=1)] = 5
    circuit_breaker_reset_seconds: Annotated[float, Field(gt=0)] = 30.0

    @model_validator(mode="after")
    def _first_token_within_request_budget(self) -> Self:
        if self.first_token_timeout_seconds > self.request_timeout_seconds:
            raise ValueError("first_token_timeout_seconds must not exceed request_timeout_seconds")
        return self


class ModelSettings(BaseModel):
    """Selection policy for the Model Gateway (the *which*)."""

    default_model: str = "mock-analyst-1"
    fallback_models: list[str] = Field(default_factory=lambda: ["mock-analyst-mini"])

    @model_validator(mode="after")
    def _default_not_in_fallbacks(self) -> Self:
        if self.default_model in self.fallback_models:
            raise ValueError("default_model must not also be listed in fallback_models")
        return self


class MockProviderSettings(BaseModel):
    """M0-only knobs for the deterministic provider used in dev and tests."""

    chunk_delay_ms: Annotated[int, Field(ge=0, le=5_000)] = 0
    words_per_chunk: Annotated[int, Field(ge=1, le=50)] = 4


class OpenAICompatibleProviderSettings(BaseModel):
    """Settings for a real chat-completions-compatible provider."""

    enabled: bool = False
    api_key: SecretStr | None = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    model_key: str = "openai-compatible-chat"
    display_name: str = "OpenAI-Compatible Chat"
    context_window: Annotated[int, Field(gt=0)] = 128_000
    max_output_tokens: Annotated[int, Field(gt=0)] = 16_384
    connect_timeout_seconds: Annotated[float, Field(gt=0)] = 10.0
    request_timeout_seconds: Annotated[float, Field(gt=0)] = 60.0

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        stripped = value.rstrip("/")
        if not stripped.startswith(("https://", "http://")):
            raise ValueError("base_url must start with http:// or https://")
        return stripped

    @model_validator(mode="after")
    def _validate_enabled_provider(self) -> Self:
        if self.enabled and self.api_key is None:
            raise ValueError("api_key is required when openai_compatible.enabled is true")
        if self.max_output_tokens > self.context_window:
            raise ValueError("max_output_tokens cannot exceed context_window")
        return self


class BillingSettings(BaseModel):
    """Usage limits and rate-limiter behavior."""

    enabled: bool = True
    rate_limit_fail_open: bool = True
    user_rate_limit_enabled: bool = False


class PolicySettings(BaseModel):
    """Deterministic security policy behavior."""

    enabled: bool = True
    profile: Literal["default", "strict", "enterprise"] = "default"
    abuse_threshold: Annotated[int, Field(ge=1)] = 5
    abuse_window_seconds: Annotated[int, Field(ge=1)] = 300


class BuildSettings(BaseModel):
    """Safe build metadata surfaced in health/meta endpoints."""

    commit: str = "unknown"
    time: str = "unknown"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CYBERAI_",
        env_nested_delimiter="__",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = Environment.LOCAL
    debug: bool = False
    version: str = "0.1.0"
    build: BuildSettings = Field(default_factory=BuildSettings)

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    mock: MockProviderSettings = Field(default_factory=MockProviderSettings)
    openai_compatible: OpenAICompatibleProviderSettings = Field(
        default_factory=OpenAICompatibleProviderSettings
    )
    billing: BillingSettings = Field(default_factory=BillingSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    @model_validator(mode="after")
    def _enforce_deployment_safety(self) -> Self:
        """Refuse to start a deployed environment with development defaults."""
        if self.app.expose_docs is None:
            self.app.expose_docs = not self.environment.is_deployed
        if not self.environment.is_deployed:
            return self

        problems: list[str] = []
        if self.debug:
            problems.append("debug must be false outside local/ci")
        if self.logging.format != "json":
            problems.append("logging.format must be 'json' outside local/ci")
        if _database_uses_insecure_default(self.database.url):
            problems.append("database.url still contains a development password")
        if "localhost" in self.database.url:
            problems.append("database.url still points at localhost")
        if any(origin == "*" for origin in self.app.cors_origins):
            problems.append("app.cors_origins must not be a wildcard")
        if not self.app.cors_origins:
            problems.append("app.cors_origins must be explicit")
        if any(host == "*" for host in self.app.trusted_hosts):
            problems.append("app.trusted_hosts must not be a wildcard")
        if not self.app.trusted_hosts:
            problems.append("app.trusted_hosts must be explicit")
        if self.app.expose_docs:
            problems.append("app.expose_docs must be false outside local/ci")
        if self.auth.jwt_secret == _DEV_AUTH_JWT_SECRET:
            problems.append("auth.jwt_secret still contains a development secret")
        if self.auth.legacy_bearer_enabled:
            problems.append("legacy bearer authentication must be disabled outside local/ci")
        if not self.auth.oidc_enabled:
            problems.append("auth.oidc_enabled must be true outside local/ci")
        if self.auth.oidc_auto_provision_enabled:
            problems.append("auth.oidc_auto_provision_enabled must be false outside local/ci")
        if not self.auth.oidc_issuer:
            problems.append("auth.oidc_issuer must be configured outside local/ci")
        if not self.auth.oidc_client_id:
            problems.append("auth.oidc_client_id must be configured outside local/ci")
        if self.auth.oidc_client_secret is None:
            problems.append("auth.oidc_client_secret must be configured outside local/ci")
        if self.auth.session_secret is None:
            problems.append("auth.session_secret must be configured outside local/ci")
        if self.auth.csrf_secret is None:
            problems.append("auth.csrf_secret must be configured outside local/ci")
        if self.auth.session_secure_cookie is False:
            problems.append("auth.session_secure_cookie must be true outside local/ci")
        configured_models = [self.models.default_model, *self.models.fallback_models]
        if any(model.startswith("mock-") for model in configured_models):
            problems.append("mock models are not allowed outside local/ci")
        if not self.openai_compatible.enabled:
            problems.append("openai_compatible provider must be enabled outside local/ci")
        if not self.policy.enabled:
            problems.append("policy.enabled must be true outside local/ci")

        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_local(self) -> bool:
        return self.environment is Environment.LOCAL


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, validated once."""
    try:
        return Settings()
    except Exception as exc:
        raise ConfigurationError(f"Invalid configuration: {exc}") from exc


def load_settings(env_file: Path | None = None, **overrides: object) -> Settings:
    """Build a settings object without touching the cache (used by tests)."""
    kwargs: dict[str, Any] = {}
    if env_file is not None:
        kwargs["_env_file"] = env_file
    kwargs.update(overrides)
    return Settings(**kwargs)
