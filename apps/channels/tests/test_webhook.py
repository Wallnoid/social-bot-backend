"""
Tests for the Meta webhook that wanps-core serves for this backend.
"""

import json

import pytest
from wanps.messaging.models import App


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="secret", verify_token="verify-me")


def test_webhook_answers_the_meta_verification_challenge(client, meta_app):
    response = client.get(
        f"/webhooks/meta/{meta_app.webhook_key}/",
        {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"},
    )

    assert response.status_code == 200
    assert response.content == b"12345"


def test_the_webhook_without_an_app_key_is_not_served(client, meta_app):
    # Without a key there is no app secret to check the signature against
    response = client.post(
        "/webhooks/meta/",
        data=json.dumps({"object": "page", "entry": []}),
        content_type="application/json",
    )

    assert response.status_code == 404
