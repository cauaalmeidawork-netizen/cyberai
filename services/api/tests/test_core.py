"""Configuration tests."""

from __future__ import annotations

import re

import pytest

from cyberai.container import build_services, shutdown_services
from cyberai.core.config import Environment, Settings, load_settings, mask_credentials
from cyberai.core.context import bind_context, current_context


def test_environment_is_local_by_default() -> None:
    settings = Settings()
    assert settings.environment == Environment.LOCAL


def test_openai_compatible_provider_is_disabled_by_default() -> None:
    settings = Settings()
    assert settings.openai_compatible.enabled is False


def test_openai_compatible_provider_requires_api_key_when_enabled() -> None:
    with pytest.raises(ValueError, match="api_key is required"):
        load_settings(openai_compatible={"enabled": True, "api_key": None})


def test_database_url_requires_async_driver() -> None:
    with pytest.raises(ValueError, match="asyncpg"):
        load_settings(
            database={
                "url": "postgresql://user:pass@localhost/db",
            }
        )


def test_redis_url_validates_scheme() -> None:
    with pytest.raises(ValueError, match="redis://"):
        load_settings(redis={"url": "http://localhost:6379"})


def test_deployment_safety_refuses_debug() -> None:
    with pytest.raises(ValueError, match="debug must be false"):
        load_settings(
            environment=Environment.PRODUCTION,
            debug=True,
        )


def test_deployment_safety_refuses_localhost_database() -> None:
    with pytest.raises(ValueError, match="localhost"):
        load_settings(
            environment=Environment.PRODUCTION,
            debug=False,
            logging={"format": "json"},
        )


def test_production_refuses_mock_default_model() -> None:
    with pytest.raises(ValueError, match="mock models are not allowed"):
        load_settings(
            environment=Environment.PRODUCTION,
            debug=False,
            logging={"format": "json"},
            database={"url": "postgresql+asyncpg://cyberai:strong-secret@db.internal/cyberai"},
            redis={"url": "redis://redis.internal:6379/0"},
            auth={"jwt_secret": "prod-jwt-secret-with-enough-entropy"},
            app={
                "cors_origins": ["https://app.cyberai.example"],
                "trusted_hosts": ["api.cyberai.example"],
            },
            openai_compatible={
                "enabled": True,
                "api_key": "sk-test-prod-config-only",
            },
        )


def test_production_refuses_mock_fallback_model() -> None:
    with pytest.raises(ValueError, match="mock models are not allowed"):
        load_settings(
            environment=Environment.PRODUCTION,
            debug=False,
            logging={"format": "json"},
            database={"url": "postgresql+asyncpg://cyberai:strong-secret@db.internal/cyberai"},
            redis={"url": "redis://redis.internal:6379/0"},
            auth={"jwt_secret": "prod-jwt-secret-with-enough-entropy"},
            app={
                "cors_origins": ["https://app.cyberai.example"],
                "trusted_hosts": ["api.cyberai.example"],
            },
            models={
                "default_model": "openai-compatible-chat",
                "fallback_models": ["mock-analyst-mini"],
            },
            openai_compatible={
                "enabled": True,
                "api_key": "sk-test-prod-config-only",
            },
        )


def test_production_accepts_real_provider_and_disables_docs_by_default() -> None:
    settings = load_settings(
        environment=Environment.PRODUCTION,
        debug=False,
        logging={"format": "json"},
        database={"url": "postgresql+asyncpg://cyberai:strong-secret@db.internal/cyberai"},
        redis={"url": "redis://redis.internal:6379/0"},
        auth=_prod_auth_settings(),
        app={
            "cors_origins": ["https://app.cyberai.example"],
            "trusted_hosts": ["api.cyberai.example"],
        },
        models={"default_model": "openai-compatible-chat", "fallback_models": []},
        openai_compatible={
            "enabled": True,
            "api_key": "sk-test-prod-config-only",
        },
        billing=_prod_billing_settings(),
    )

    assert settings.app.expose_docs is False
    assert settings.models.default_model == "openai-compatible-chat"
    assert settings.build.commit == "unknown"


@pytest.mark.asyncio
async def test_production_service_graph_does_not_register_mock_provider() -> None:
    settings = load_settings(
        environment=Environment.PRODUCTION,
        debug=False,
        logging={"format": "json"},
        database={"url": "postgresql+asyncpg://cyberai:strong-secret@db.internal/cyberai"},
        redis={"url": "redis://redis.internal:6379/0"},
        auth=_prod_auth_settings(),
        app={
            "cors_origins": ["https://app.cyberai.example"],
            "trusted_hosts": ["api.cyberai.example"],
        },
        models={"default_model": "openai-compatible-chat", "fallback_models": []},
        openai_compatible={
            "enabled": True,
            "api_key": "sk-test-prod-config-only",
        },
        billing=_prod_billing_settings(),
    )
    services = build_services(settings)
    try:
        assert services.providers.has("mock") is False
        assert services.providers.has("openai-compatible") is True
    finally:
        await shutdown_services(services)


def test_mask_credentials_redacts_password() -> None:
    url = "postgresql+asyncpg://user:S3cr3t@db.internal:5432/cyberai"
    assert mask_credentials(url) == "postgresql+asyncpg://user:***@db.internal:5432/cyberai"


def _prod_auth_settings() -> dict[str, object]:
    return {
        "jwt_secret": "prod-jwt-secret-with-enough-entropy",
        "legacy_bearer_enabled": False,
        "oidc_enabled": True,
        "oidc_issuer": "https://idp.cyberai.example",
        "oidc_client_id": "cyberai",
        "oidc_client_secret": "prod-client-secret",
        "oidc_redirect_uri": "https://api.cyberai.example/api/v1/auth/callback",
        "session_secret": "prod-session-secret-with-enough-entropy",
        "csrf_secret": "prod-csrf-secret-with-enough-entropy",
        "session_secure_cookie": True,
    }


def _prod_billing_settings() -> dict[str, object]:
    return {
        "provider": "stripe",
        "stripe_secret_key": "sk_live_config_test",
        "stripe_webhook_secret": "whsec_config_test",
        "stripe_price_ids": {"pro": "price_pro", "business": "price_business"},
        "checkout_success_url": "https://app.cyberai.example/billing/success",
        "checkout_cancel_url": "https://app.cyberai.example/billing/cancel",
        "portal_return_url": "https://app.cyberai.example/billing",
    }


def test_uuid7_sortable_and_unique() -> None:
    from cyberai.core.ids import new_uuid7

    ids = [new_uuid7() for _ in range(20)]
    assert len({str(uid) for uid in ids}) == len(ids)
    # The monotonic counter guarantees strict ordering by raw integer value.
    assert ids == sorted(ids, key=lambda uid: uid.int)


def test_request_context_binding_is_isolated() -> None:
    ctx = current_context()
    assert ctx.request_id is None

    with bind_context(request_id="req-1", org_id="org-1"):
        assert current_context().request_id == "req-1"
        assert current_context().org_id == "org-1"

    assert current_context().request_id is None


def test_log_redaction_masks_sensitive_keys() -> None:
    from cyberai.core.logging import redact_processor

    event = {
        "api_key": "secret",
        "database_url": "postgresql://user:pass@host/db",
        "nested": {"authorization": "Bearer abc", "ok": "value"},
    }
    result = redact_processor(None, "info", event)
    assert result["api_key"] == "***redacted***"
    assert "***" in result["database_url"]
    assert result["nested"]["authorization"] == "***redacted***"
    assert result["nested"]["ok"] == "value"


def test_safe_request_id_header_accepted() -> None:
    from cyberai.api.middleware.request_context import _sanitize_request_id

    assert _sanitize_request_id("abc-123.def:XYZ_") == "abc-123.def:XYZ_"


def test_request_id_sanitizes_injection() -> None:
    from cyberai.api.middleware.request_context import _sanitize_request_id

    sanitized = _sanitize_request_id("abc\n../../etc/passwd")
    assert sanitized != "abc\n../../etc/passwd"
    # Must still be a valid UUID-like string.
    assert re.match(r"^[0-9a-f-]{36}$", sanitized)


def test_traceparent_extraction() -> None:
    from cyberai.api.middleware.request_context import _extract_trace_id

    assert (
        _extract_trace_id("00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
        == "0af7651916cd43dd8448eb211c80319c"
    )


def test_traceparent_invalid_trace_id_fallback() -> None:
    from cyberai.api.middleware.request_context import _extract_trace_id

    # All-zeros trace id is invalid by W3C spec.
    new_trace = _extract_trace_id("00-00000000000000000000000000000000-0000000000000000-00")
    assert len(new_trace) == 32
    assert new_trace != "0" * 32
