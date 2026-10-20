import json
from pathlib import Path

from smartploy.worker_runtime import build_worker_task_specs


ENV_KEYS = [
    "KUNTAREKRY_FEED_URL",
    "JOBMARKET_FINLAND_API_ENABLED",
    "JOBMARKET_FINLAND_ENVIRONMENT",
    "JOBMARKET_FINLAND_ENDPOINT",
    "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY",
    "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON",
    "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE",
    "OBUMAI_BASE_URL",
    "OBUMAI_HTTP_HEADERS_JSON",
    "SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED",
    "SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED",
    "SMARTPLOY_ENVIRONMENT",
]


def clear_worker_sources(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_unconfigured_sources_and_obumai_create_no_worker_tasks(monkeypatch):
    clear_worker_sources(monkeypatch)
    assert build_worker_task_specs("postgresql://fixture") == []


def test_public_ats_creates_one_task_per_configured_tenant(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv(
        "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON",
        json.dumps(
            [
                {
                    "provider": "smartrecruiters",
                    "tenant": "acme",
                    "label": "Acme Oy",
                    "employer_sector": "private",
                },
                {
                    "provider": "lever",
                    "tenant": "example",
                    "label": "Example Oy",
                    "stack": "eu",
                    "employer_sector": "private",
                },
            ]
        ),
    )
    specs = build_worker_task_specs("postgresql://fixture")
    assert {item.task_id for item in specs} == {
        "source:smartrecruiters-acme",
        "source:lever-eu-example",
    }


def test_jobmarket_task_metadata_contains_no_subscription_key(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("JOBMARKET_FINLAND_API_ENABLED", "true")
    monkeypatch.setenv("JOBMARKET_FINLAND_ENVIRONMENT", "test")
    monkeypatch.setenv("JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY", "super-secret-key")
    specs = build_worker_task_specs("postgresql://fixture")
    assert [item.task_id for item in specs] == ["source:job-market-finland"]
    assert "super-secret-key" not in json.dumps(dict(specs[0].metadata or {}))


def test_configured_obumai_only_refreshes_existing_jobs_by_default(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    specs = build_worker_task_specs("postgresql://fixture")
    assert {item.task_id for item in specs} == {
        "application:refresh-preparations",
    }
    assert all(
        dict(item.metadata or {}).get("external_actions_authorized") is False
        for item in specs
    )


def test_legacy_unattended_preparation_requires_explicit_operator_opt_in(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "test")
    specs = build_worker_task_specs("postgresql://fixture")
    assert {item.task_id for item in specs} == {
        "application:prepare-eligible",
        "application:refresh-preparations",
    }
    prepare = next(item for item in specs if item.task_id == "application:prepare-eligible")
    assert prepare.metadata["unattended_model_processing_opt_in"] is True
    assert all(
        dict(item.metadata or {}).get("external_actions_authorized") is False
        for item in specs
    )


def test_stale_autoprepare_task_is_not_in_registry_when_flag_is_turned_off(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "test")
    active = build_worker_task_specs("postgresql://fixture")
    assert any(item.task_id == "application:prepare-eligible" for item in active)
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "false")
    after = build_worker_task_specs("postgresql://fixture")
    assert all(item.task_id != "application:prepare-eligible" for item in after)
    assert any(item.task_id == "application:refresh-preparations" for item in after)


def test_invalid_or_unconfigured_autoprepare_flags_fail_closed(monkeypatch):
    import pytest
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    for invalid in ("1", "yes", "enabled", "", "maybe", "TRUE-with-note"):
        if invalid == "":
            # Empty is not explicit authorization even if one is present.
            # Fail closed rather than silently converting a typo to true.
            monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", invalid)
        else:
            monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", invalid)
        with pytest.raises(ValueError, match="must be literal true or false"):
            build_worker_task_specs("postgresql://fixture")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "true")
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "test")
    monkeypatch.delenv("OBUMAI_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="without ObumAI configuration"):
        build_worker_task_specs("postgresql://fixture")



def test_global_unattended_worker_flag_fails_closed_in_production(monkeypatch):
    import pytest
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "true")
    for mode in (None, "production", "PRODUCTION", "staging", ""):
        if mode is None:
            monkeypatch.delenv("SMARTPLOY_ENVIRONMENT", raising=False)
        else:
            monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", mode)
        with pytest.raises(ValueError, match="unavailable in production"):
            build_worker_task_specs("postgresql://fixture")


def test_explicit_nonproduction_flag_can_register_legacy_fixture_only(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "true")
    for mode in ("test", "development"):
        monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", mode)
        specs = build_worker_task_specs("postgresql://fixture")
        assert {item.task_id for item in specs} == {
            "application:refresh-preparations", "application:prepare-eligible"
        }


def test_production_false_flag_keeps_source_poll_and_refresh_tasks(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED", "false")
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ATS_SOURCES_JSON", json.dumps([{
        "provider": "lever", "tenant": "fictional", "label": "Fictional Oy"
    }]))
    specs = build_worker_task_specs("postgresql://fixture")
    assert {item.task_id for item in specs} == {
        "application:refresh-preparations", "source:lever-global-fictional"
    }


def test_systemd_worker_unit_contains_no_credentials():
    text = Path("deploy/systemd/smartploy-source-worker.service.example").read_text(
        encoding="utf-8"
    )
    assert "EnvironmentFile=/etc/smartploy/smartploy.env" in text
    assert "Restart=always" in text
    assert "KIPA-Subscription-Key" not in text
    assert "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY=" not in text
    assert "OBUMAI_HTTP_HEADERS_JSON=" not in text


def test_scoped_local_draft_worker_runs_without_remote_ai_or_global_submit(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "production")
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED", "true")
    specs = build_worker_task_specs("postgresql://fixture")
    assert {s.task_id for s in specs} == {"application:auto-draft-shortlist"}
    one=specs[0]
    assert one.cadence_seconds == 600
    assert one.metadata["private_opt_in_required"] is True
    assert one.metadata["processing"] == "local_only"
    assert one.metadata["external_actions_authorized"] is False
    monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED", "false")
    assert build_worker_task_specs("postgresql://fixture") == []
    for bad in ("yes","1","fast",""):
        monkeypatch.setenv("SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED", bad)
        import pytest
        with pytest.raises(ValueError, match="must be true or false"):
            build_worker_task_specs("postgresql://fixture")
