from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smartploy.api import create_app
from smartploy.service import SmartployService


ROOT = Path(__file__).resolve().parents[1]


def test_public_origin_and_allowed_host(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.obumai.com")
    api = TestClient(create_app(SmartployService()), base_url="https://smartploy.obumai.com")

    response = api.get("/healthz")
    assert response.status_code == 200
    assert response.json()["public_origin"] == "https://smartploy.obumai.com"

    rejected = api.get("/healthz", headers={"host": "evil.example"})
    assert rejected.status_code == 400


def test_new_komplyint_origin_is_exactly_host_bound(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.komplyint.fi")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "smartploy.komplyint.fi")
    api = TestClient(
        create_app(SmartployService()),
        base_url="https://smartploy.komplyint.fi",
    )
    health = api.get("/healthz")
    assert health.status_code == 200
    assert health.json()["public_origin"] == "https://smartploy.komplyint.fi"
    assert api.get("/healthz", headers={"host": "smartploy.obumai.com"}).status_code == 400
    assert api.get("/healthz", headers={"host": "untrusted.komplyint.fi"}).status_code == 400


def test_invalid_public_origin_and_wildcard_host_fail_closed(monkeypatch):
    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "http://smartploy.obumai.com")
    with pytest.raises(ValueError, match="HTTPS"):
        create_app(SmartployService())

    monkeypatch.setenv("SMARTPLOY_PUBLIC_ORIGIN", "https://smartploy.obumai.com")
    monkeypatch.setenv("SMARTPLOY_ALLOWED_HOSTS", "*.obumai.com")
    with pytest.raises(ValueError, match="exact host"):
        create_app(SmartployService())


def test_deployment_files_keep_secrets_out_and_same_origin_in():
    nginx = (ROOT / "deploy/nginx/smartploy.obumai.com.conf.example").read_text(encoding="utf-8")
    unit = (ROOT / "deploy/systemd/smartploy-api.service.example").read_text(encoding="utf-8")

    assert "server_name smartploy.obumai.com;" in nginx
    assert "proxy_pass http://127.0.0.1:8090" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx
    assert "frame-ancestors 'none'" in nginx
    assert "connect-src 'self'" in nginx
    assert "Access-Control-Allow-Origin" not in nginx
    assert "proxy_set_header Cf-Access-Jwt-Assertion $http_cf_access_jwt_assertion;" in nginx

    assert "EnvironmentFile=/etc/smartploy/smartploy.env" in unit
    assert "--host 127.0.0.1" in unit
    assert "PASSWORD=" not in unit
    assert "TOKEN=" not in unit
    assert "KIPA" not in unit
