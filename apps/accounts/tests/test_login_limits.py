"""
Tests for the login rate limit and the daily cleanup of expired tokens.
"""

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tasks import flush_expired_tokens

User = get_user_model()

LOGIN_URL = "/api/v1/accounts/token/"
EMAIL = "owner@acme.test"
PASSWORD = "OldPass123!"


@pytest.fixture
def owner(db):
    return User.objects.create_user(email=EMAIL, password=PASSWORD)


def log_in(api, password=PASSWORD, **headers):
    return api.post(LOGIN_URL, {"email": EMAIL, "password": password}, format="json", **headers)


@pytest.mark.django_db
def test_login_is_limited_to_five_attempts_per_minute(owner):
    api = APIClient()

    answers = [log_in(api, "wrong-password").status_code for _ in range(5)]
    assert answers == [401] * 5

    # Even the right password is refused once the limit is reached
    assert log_in(api).status_code == 429


@pytest.mark.django_db
def test_successful_logins_count_too(owner):
    api = APIClient()
    for _ in range(5):
        assert log_in(api).status_code == 200

    assert log_in(api).status_code == 429


@pytest.mark.django_db
def test_each_client_has_its_own_limit(owner):
    first = APIClient(REMOTE_ADDR="10.0.0.1")
    second = APIClient(REMOTE_ADDR="10.0.0.2")
    for _ in range(5):
        log_in(first, "wrong-password")

    assert log_in(first).status_code == 429
    assert log_in(second).status_code == 200


@pytest.mark.django_db
def test_a_forged_forwarded_header_does_not_reset_the_limit(owner):
    api = APIClient(REMOTE_ADDR="10.0.0.1")
    for attempt in range(5):
        log_in(api, "wrong-password", HTTP_X_FORWARDED_FOR=f"1.2.3.{attempt}")

    assert log_in(api, HTTP_X_FORWARDED_FOR="9.9.9.9").status_code == 429


def test_the_client_is_told_apart_by_its_socket_address_unless_proxies_are_declared():
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0


@pytest.mark.django_db
def test_flush_expired_tokens_deletes_only_the_expired_ones(owner):
    expired = RefreshToken.for_user(owner)
    expired_revoked = RefreshToken.for_user(owner)
    valid = RefreshToken.for_user(owner)
    expired_revoked.blacklist()
    OutstandingToken.objects.filter(jti__in=[expired["jti"], expired_revoked["jti"]]).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    flush_expired_tokens()

    assert list(OutstandingToken.objects.values_list("jti", flat=True)) == [valid["jti"]]
    assert not BlacklistedToken.objects.exists()


def test_flush_expired_tokens_runs_every_day():
    entry = settings.CELERY_BEAT_SCHEDULE["flush-expired-tokens"]

    assert entry["task"] == "apps.accounts.tasks.flush_expired_tokens"
    assert entry["schedule"] == 24 * 60 * 60
