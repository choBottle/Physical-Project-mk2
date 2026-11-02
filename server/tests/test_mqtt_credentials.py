"""MQTT 계정(opt-in) — ingest 클라이언트·시험 발행자가 MK2_MQTT_USERNAME/PASSWORD 를 싣는가.

브로커 없이 돈다: 클라이언트 **구성**만 본다(접속하지 않는다). 실제 브로커에서 계정 접속 성공·익명 거부는
deploy/scripts/mqtt-auth-check.sh(deploy-smoke `mqtt-auth` 잡)가 본다.

implements: BE-T-01
tests: 계정 설정 시 username/password 부착(양성) · 미설정·username 빈 값이면 익명(음성 대조)
"""

from __future__ import annotations

import pytest

from backend import settings
from backend.ingest import bridge


@pytest.fixture
def no_mqtt_auth(monkeypatch):
    monkeypatch.delenv("MK2_MQTT_USERNAME", raising=False)
    monkeypatch.delenv("MK2_MQTT_PASSWORD", raising=False)


def test_credentials_default_anonymous(no_mqtt_auth):
    assert settings.mqtt_credentials() is None


def test_credentials_password_without_username_is_anonymous(no_mqtt_auth, monkeypatch):
    monkeypatch.setenv("MK2_MQTT_PASSWORD", "secret")
    assert settings.mqtt_credentials() is None


def test_ingest_client_carries_credentials(no_mqtt_auth, monkeypatch):
    monkeypatch.setenv("MK2_MQTT_USERNAME", "mk2-backend")
    monkeypatch.setenv("MK2_MQTT_PASSWORD", "s3cret")
    client = bridge.make_mqtt_client("mk2-test")
    assert client.username == "mk2-backend"
    assert client.password == "s3cret"


def test_ingest_client_anonymous_when_unset(no_mqtt_auth):
    client = bridge.make_mqtt_client("mk2-test")
    assert client.username is None
    assert client.password is None


def test_publisher_passes_auth(no_mqtt_auth, monkeypatch):
    import publisher

    calls = []
    monkeypatch.setattr(publisher.mqtt_publish, "single", lambda *a, **kw: calls.append(kw))

    publisher.publish("zoneA/sensor/wl-001/state", {"x": 1}, host="h", port=1)
    assert calls[-1]["auth"] is None

    monkeypatch.setenv("MK2_MQTT_USERNAME", "mk2-backend")
    monkeypatch.setenv("MK2_MQTT_PASSWORD", "s3cret")
    publisher.publish("zoneA/sensor/wl-001/state", {"x": 1}, host="h", port=1)
    assert calls[-1]["auth"] == {"username": "mk2-backend", "password": "s3cret"}
