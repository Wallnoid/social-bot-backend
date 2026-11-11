"""
Tests for closing the other sessions when the password changes.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()

COOKIE = "refresh_token"
EMAIL = "owner@acme.test"
PASSWORD = "OldPass123!"
NEW_PASSWORD = "NewPass456!"
AJAX = {"HTTP_X_REQUESTED_WITH": "fetch"}
ME_URL = "/api/v1/accounts/users/me/"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; start every test from zero."""
    cache.clear()


@pytest.fixture
def owner(db):
    return User.objects.create_user(email=EMAIL, password=PASSWORD, first_name="Olivia")


def logged_in_device(password=PASSWORD):
    """An API client logged in like the frontend: access in the header, refresh in the cookie."""
    api = APIClient()
    response = api.post(
        reverse("accounts:token_obtain_pair"),
        {"email": EMAIL, "password": password},
        format="json",
    )
    assert response.status_code == 200
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return api


def can_read_profile(api):
    return api.get(ME_URL).status_code == 200


def refresh(api):
    return api.post(reverse("accounts:token_refresh"), **AJAX)


def change_password(api):
    return api.post(
        reverse("accounts:user-change-password"),
        {
            "old_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )


def reset_password_with_emailed_link(mailoutbox):
    APIClient().post("/api/v1/accounts/password-reset/", {"email": EMAIL}, format="json")
    uid, token = re.search(r"uid=([^&\s]+)&token=(\S+)", mailoutbox[-1].body).groups()
    return APIClient().post(
        "/api/v1/accounts/set-password/",
        {
            "uid": uid,
            "token": token,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )


@pytest.mark.django_db
def test_reset_closes_every_session(owner, mailoutbox):
    device = logged_in_device()

    assert reset_password_with_emailed_link(mailoutbox).status_code == 200

    assert not can_read_profile(device)
    assert refresh(device).status_code == 401


@pytest.mark.django_db
def test_change_password_closes_the_other_sessions(owner):
    this_device = logged_in_device()
    other_device = logged_in_device()

    assert change_password(this_device).status_code == 200

    assert not can_read_profile(other_device)
    assert refresh(other_device).status_code == 401


@pytest.mark.django_db
def test_change_password_keeps_this_device_logged_in(owner):
    device = logged_in_device()

    response = change_password(device)

    assert response.status_code == 200
    assert response.data["message"] == "Password changed successfully."
    assert response.cookies[COOKIE].value
    assert response.cookies[COOKIE]["httponly"]
    device.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    assert can_read_profile(device)
    assert refresh(device).status_code == 200


@pytest.mark.django_db
def test_change_password_revokes_the_old_refresh_tokens(owner, settings):
    # Even without the password claim, the old refresh tokens are blacklisted
    other_device = logged_in_device()
    settings.SIMPLE_JWT = {**settings.SIMPLE_JWT, "CHECK_REVOKE_TOKEN": False}
    from rest_framework_simplejwt.settings import api_settings

    api_settings.reload()
    try:
        assert change_password(logged_in_device()).status_code == 200
        assert refresh(other_device).status_code == 401
    finally:
        settings.SIMPLE_JWT = {**settings.SIMPLE_JWT, "CHECK_REVOKE_TOKEN": True}
        api_settings.reload()


@pytest.mark.django_db
def test_password_changed_outside_the_api_closes_every_session(owner):
    device = logged_in_device()

    owner.set_password(NEW_PASSWORD)
    owner.save()

    rejected = device.get(ME_URL)
    assert rejected.status_code == 401
    assert rejected.data["code"] == "password_changed"
    assert rejected.data["message"] == "The user's password has been changed."
    response = refresh(device)
    assert response.status_code == 401
    assert response.data["code"] == "password_changed"
    assert can_read_profile(logged_in_device(NEW_PASSWORD))


@pytest.mark.django_db
def test_editing_the_profile_keeps_the_session(owner):
    device = logged_in_device()

    assert device.patch(ME_URL, {"first_name": "Liv"}, format="json").status_code == 200

    assert can_read_profile(device)
    assert refresh(device).status_code == 200
