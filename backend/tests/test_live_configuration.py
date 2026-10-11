import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from tests.test_api import payload


def test_deepseek_configuration_defaults_and_bounds():
    settings = Settings()

    assert settings.enable_live_workflow is False
    assert Settings(enable_live_workflow=True).enable_live_workflow is True
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.deepseek_timeout_seconds == 30
    assert settings.deepseek_max_output_tokens == 4096

    with pytest.raises(ValidationError):
        Settings(deepseek_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(deepseek_timeout_seconds=121)
    with pytest.raises(ValidationError):
        Settings(deepseek_max_output_tokens=511)
    with pytest.raises(ValidationError):
        Settings(deepseek_max_output_tokens=8193)


def test_tavily_configuration_defaults_bounds_and_normalized_domains(monkeypatch):
    monkeypatch.setenv(
        "TAVILY_TRUSTED_DOMAINS",
        " Example.COM,bücher.example,example.com ",
    )
    monkeypatch.setenv(
        "TAVILY_BLOCKED_DOMAINS",
        " blocked.example,cdn.example ",
    )

    settings = Settings()

    assert settings.tavily_timeout_seconds == 15
    assert settings.tavily_trusted_domains == (
        "example.com",
        "xn--bcher-kva.example",
    )
    assert settings.tavily_blocked_domains == (
        "blocked.example",
        "cdn.example",
    )

    with pytest.raises(ValidationError):
        Settings(tavily_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(tavily_timeout_seconds=31)
    with pytest.raises(ValidationError):
        Settings(tavily_trusted_domains="https://example.com")


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("with_model_key", [False, True])
@pytest.mark.parametrize("with_search_key", [False, True])
def test_live_unlock_requires_flag_and_both_provider_keys(
    tmp_path,
    enabled,
    with_model_key,
    with_search_key,
):
    model_key = "test-model-key" if with_model_key else None
    search_key = "test-search-key" if with_search_key else None
    settings = Settings(
        app_mode="live",
        enable_live_workflow=enabled,
        deepseek_api_key=model_key,
        tavily_api_key=search_key,
    )
    unlocked = enabled and with_model_key and with_search_key
    app = create_app(
        tmp_path / "db",
        settings=settings,
        model_provider=DemoModelProvider() if unlocked else None,
        search_provider=DemoSearchProvider() if unlocked else None,
    )

    with TestClient(app) as client:
        health = client.get("/api/health").json()
        response = client.post("/api/decisions", json=payload())

    assert health == {
        "status": "ok" if unlocked else "unavailable",
        "mode": "live",
        "database": "ok",
        "live_workflow_enabled": enabled,
        "live_model_configured": with_model_key,
        "live_model_adapter_available": True,
        "live_search_configured": with_search_key,
        "live_search_adapter_available": True,
        "live_search_available": enabled and with_search_key,
        "live_available": unlocked,
    }
    assert response.status_code == (201 if unlocked else 503)
    if unlocked:
        assert response.json()["mode"] == "live"
    assert "test-model-key" not in response.text
    assert "test-search-key" not in response.text
    assert "test-model-key" not in repr(settings)
    assert "test-search-key" not in repr(settings)
    assert len(app.state.repository.list()) == int(unlocked)
    assert isinstance(app.state.workflow._model, DemoModelProvider)
    assert isinstance(app.state.workflow._search, DemoSearchProvider)


def test_demo_health_remains_available_without_live_capabilities(tmp_path):
    with TestClient(create_app(tmp_path / "db", settings=Settings())) as client:
        health = client.get("/api/health").json()

    assert health == {
        "status": "ok",
        "mode": "demo",
        "database": "ok",
        "live_workflow_enabled": False,
        "live_model_configured": False,
        "live_model_adapter_available": True,
        "live_search_configured": False,
        "live_search_adapter_available": True,
        "live_search_available": False,
        "live_available": False,
    }


def test_blank_live_keys_are_treated_as_unconfigured_without_breaking_startup(
    tmp_path,
):
    settings = Settings(
        app_mode="live",
        deepseek_api_key="   ",
        tavily_api_key="   ",
    )

    with TestClient(create_app(tmp_path / "db", settings=settings)) as client:
        health = client.get("/api/health").json()

    assert health["live_model_configured"] is False
    assert health["live_search_configured"] is False
    assert health["live_available"] is False


def test_live_never_executes_with_one_real_and_one_demo_provider(tmp_path):
    settings = Settings(
        app_mode="live",
        enable_live_workflow=True,
        deepseek_api_key="test-model-key",
        tavily_api_key=None,
    )
    app = create_app(tmp_path / "db", settings=settings)

    with TestClient(app) as client:
        assert client.post("/api/decisions", json=payload()).status_code == 503

    assert app.state.live_available is False
    assert isinstance(app.state.workflow._model, DemoModelProvider)
    assert isinstance(app.state.workflow._search, DemoSearchProvider)
