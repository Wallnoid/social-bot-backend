"""
Tests for asking for a link to reset a forgotten password.
"""

import re
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()

RESET_URL = "/api/v1/accounts/password-reset/"
SET_PASSWORD_URL = "/api/v1/accounts/set-password/"
SAME_ANSWER = "If an account uses this email, we sent it a link to reset the password."


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; start every test from zero."""
    cache.clear()


@pytest.fixture
def owner():
    return User.objects.create_user(
        email="owner@acme.test", password="OldPass123!", first_name="Olivia"
    )


def ask_reset(email, api=None):
    return (api or APIClient()).post(RESET_URL, {"email": email}, format="json")


def log_in(password):
    return APIClient().post(
        "/api/v1/accounts/token/",
        {"email": "owner@acme.test", "password": password},
        format="json",
    )


@pytest.mark.django_db
def test_reset_link_sets_a_new_password(owner, settings, mailoutbox):
    settings.FRONTEND_URL = "https://app.example.test"

    response = ask_reset("Owner@ACME.test")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["message"] == SAME_ANSWER
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["owner@acme.test"]
    match = re.search(
        r"https://app\.example\.test/set-password\?uid=([^&\s]+)&token=(\S+)", mailoutbox[0].body
    )
    reset = APIClient().post(
        SET_PASSWORD_URL,
        {
            "uid": match.group(1),
            "token": match.group(2),
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        },
        format="json",
    )
    assert reset.status_code == status.HTTP_200_OK
    assert log_in("NewPass456!").status_code == status.HTTP_200_OK
    assert log_in("OldPass123!").status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_reset_email_says_reset_and_how_long_the_link_lasts(owner, settings, mailoutbox):
    settings.PASSWORD_RESET_TIMEOUT = 60 * 60

    ask_reset("owner@acme.test")

    assert mailoutbox[0].subject == "Restablece tu contraseña de Social Bot"
    assert "Hola Olivia" in mailoutbox[0].body
    assert "válido por 1 hora" in mailoutbox[0].body


@pytest.mark.django_db
def test_unknown_email_gets_the_same_answer_and_no_email(mailoutbox):
    response = ask_reset("nobody@acme.test")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["message"] == SAME_ANSWER
    assert mailoutbox == []


@pytest.mark.django_db
def test_deactivated_user_gets_the_same_answer_and_no_email(owner, mailoutbox):
    owner.is_active = False
    owner.save()

    response = ask_reset("owner@acme.test")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["message"] == SAME_ANSWER
    assert mailoutbox == []


@pytest.mark.django_db
def test_invalid_email_is_rejected(mailoutbox):
    response = ask_reset("not-an-email")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert mailoutbox == []


@pytest.mark.django_db
def test_failed_email_still_gets_the_same_answer(owner):
    with mock.patch(
        "apps.accounts.tasks.send_password_reset_email", side_effect=OSError("SMTP down")
    ):
        response = ask_reset("owner@acme.test")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["message"] == SAME_ANSWER


@pytest.mark.django_db
def test_stale_access_token_does_not_block_the_reset(owner, mailoutbox):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-token")

    response = ask_reset("owner@acme.test", api)

    assert response.status_code == status.HTTP_200_OK
    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_reset_requests_are_throttled(owner):
    api = APIClient()
    for _ in range(5):
        assert ask_reset("owner@acme.test", api).status_code == status.HTTP_200_OK

    assert ask_reset("owner@acme.test", api).status_code == status.HTTP_429_TOO_MANY_REQUESTS
