"""No unconsented durable ObumAI forwarding through legacy HTTP routes.

These are isolated synthetic requests using mocked service methods. They do
not invoke a real model, job source, employer site, or production identity.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.service import SmartployService


@pytest.fixture
def legacy_api(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_ENVIRONMENT", "test")
    monkeypatch.setenv("SMARTPLOY_AUTH_MODE", "disabled")
    monkeypatch.delenv("SMARTPLOY_DATABASE_URL", raising=False)
    service = SmartployService()

    class DummyPreparation:
        def to_dict(self):
            return {"status": "queued", "package_id": "synthetic-package"}

    service.prepare_job = Mock(return_value=DummyPreparation())
    service.submit_obumai = Mock(return_value={
        "job": {"job_id": "synthetic-analysis", "state": "queued"},
        "external_actions_performed": False,
    })
    return TestClient(create_app(service)), service


@pytest.mark.parametrize("consent", [
    None, False, "true", 1, "", [], {},
])
def test_prepare_endpoint_never_calls_service_without_literal_true_consent(
    legacy_api, consent
):
    api, service = legacy_api
    body = {} if consent is None else {"acknowledge_obumai_processing": consent}
    response = api.post("/api/v1/jobs/fictional-job/prepare", json=body)
    assert response.status_code == 422, response.text
    service.prepare_job.assert_not_called()
    service.submit_obumai.assert_not_called()


@pytest.mark.parametrize("consent", [
    None, False, "true", 1, "", [], {},
])
def test_legacy_obumai_endpoint_does_not_forward_without_consent(
    legacy_api, consent
):
    api, service = legacy_api
    body = {"action": "fit_analysis", "instructions": "Synthetic review only"}
    if consent is not None:
        body["acknowledge_obumai_processing"] = consent
    response = api.post("/api/v1/jobs/fictional-job/obumai", json=body)
    assert response.status_code == 422, response.text
    service.submit_obumai.assert_not_called()


@pytest.mark.parametrize("action", [
    "apply_to_employer", "submit_application", "browse", "send_email",
    "upload_cv", "deploy", "custom_action",
])
def test_unknown_obumai_actions_do_not_dispatch_even_with_consent(legacy_api, action):
    api, service = legacy_api
    response = api.post("/api/v1/jobs/fictional-job/obumai", json={
        "action": action,
        "acknowledge_obumai_processing": True,
    })
    assert response.status_code == 422, response.text
    service.submit_obumai.assert_not_called()


def test_explicit_opt_in_allows_legacy_preparation_without_empowerment(legacy_api):
    api, service = legacy_api
    response = api.post("/api/v1/jobs/fictional-job/prepare", json={
        "acknowledge_obumai_processing": True,
    })
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "queued", "package_id": "synthetic-package"}
    service.prepare_job.assert_called_once_with("fictional-job")
    service.submit_obumai.assert_not_called()


@pytest.mark.parametrize("action", ["fit_analysis", "application_package_v1"])
def test_explicit_opt_in_allows_only_approved_reasoning_actions(legacy_api, action):
    api, service = legacy_api
    response = api.post("/api/v1/jobs/fictional-job/obumai", json={
        "action": action,
        "instructions": "Use approved evidence only, no external action.",
        "acknowledge_obumai_processing": True,
    })
    assert response.status_code == 200, response.text
    assert response.json()["external_actions_performed"] is False
    service.submit_obumai.assert_called_once_with(
        "fictional-job", action=action,
        instructions="Use approved evidence only, no external action.",
    )
    service.prepare_job.assert_not_called()


def test_legacy_requests_cannot_smuggle_approval_via_extra_fields(legacy_api):
    api, service = legacy_api
    response = api.post("/api/v1/jobs/fictional-job/obumai", json={
        "action": "fit_analysis",
        "acknowledge_obumai_processing": True,
        "authorize_browser_submission": True,
    })
    assert response.status_code == 422, response.text
    service.submit_obumai.assert_not_called()
