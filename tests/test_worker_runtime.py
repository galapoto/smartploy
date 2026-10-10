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


def test_application_tasks_exist_only_when_obumai_is_configured(monkeypatch):
    clear_worker_sources(monkeypatch)
    monkeypatch.setenv("OBUMAI_BASE_URL", "http://127.0.0.1:8088")
    specs = build_worker_task_specs("postgresql://fixture")
    assert {item.task_id for item in specs} == {
        "application:prepare-eligible",
        "application:refresh-preparations",
    }
    assert all(
        dict(item.metadata or {}).get("external_actions_authorized") is False
        for item in specs
    )


def test_systemd_worker_unit_contains_no_credentials():
    text = Path("deploy/systemd/smartploy-source-worker.service.example").read_text(
        encoding="utf-8"
    )
    assert "EnvironmentFile=/etc/smartploy/smartploy.env" in text
    assert "Restart=always" in text
    assert "KIPA-Subscription-Key" not in text
    assert "JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY=" not in text
    assert "OBUMAI_HTTP_HEADERS_JSON=" not in text
