"""
The refresh token travels in an httpOnly cookie, never in the body.
"""

import os
import subprocess
import sys
from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

COOKIE = "refresh_token"
EMAIL = "testuser@example.com"
PASSWORD = "testpass123"
# Any value works: a form on another site cannot send this header
AJAX = {"HTTP_X_REQUESTED_WITH": "fetch"}


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email=EMAIL, password=PASSWORD, first_name="Test", last_name="User"
    )


def log_in(api):
    return api.post(
        reverse("accounts:token_obtain_pair"),
        {"email": EMAIL, "password": PASSWORD},
        format="json",
    )


def test_login_returns_the_access_token_and_puts_the_refresh_token_in_an_httponly_cookie(
    api_client, user
):
    response = log_in(api_client)

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" not in response.data
    cookie = response.cookies[COOKIE]
    assert cookie.value
    assert cookie.value != response.data["access"]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Strict"
    assert cookie["path"] == "/api/v1/accounts/"
    assert int(cookie["max-age"]) == 7 * 24 * 60 * 60
    assert not cookie["domain"]


def test_the_cookie_is_secure_when_the_setting_asks_for_it(api_client, user, settings):
    assert not log_in(api_client).cookies[COOKIE]["secure"]

    settings.AUTH_REFRESH_COOKIE_SECURE = True

    assert log_in(api_client).cookies[COOKIE]["secure"]


def test_refresh_with_the_cookie_gives_a_new_access_token_and_replaces_the_cookie(api_client, user):
    first = log_in(api_client).cookies[COOKIE].value

    response = api_client.post(reverse("accounts:token_refresh"), **AJAX)

    assert response.status_code == 200
    assert "refresh" not in response.data
    me = api_client.get(
        reverse("accounts:user-me"), HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
    )
    assert me.status_code == 200
    replaced = response.cookies[COOKIE]
    assert replaced.value and replaced.value != first
    assert replaced["httponly"] and replaced["samesite"] == "Strict"
    assert replaced["path"] == "/api/v1/accounts/"


def refresh(api, **extra):
    return api.post(reverse("accounts:token_refresh"), **extra)


def test_the_previous_refresh_token_stops_working_after_a_refresh(api_client, user):
    first = log_in(api_client).cookies[COOKIE].value
    assert refresh(api_client, **AJAX).status_code == 200

    # Someone replays the token that was just replaced
    api_client.cookies[COOKIE] = first
    response = refresh(api_client, **AJAX)

    assert response.status_code == 401
    assert "access" not in response.data


def expired_token(user):
    token = RefreshToken.for_user(user)
    token.set_exp(from_time=timezone.now() - timedelta(days=8))
    return str(token)


@pytest.mark.parametrize("cookie", ["no cookie", "not-a-token", "expired"])
def test_refresh_without_a_valid_cookie_is_rejected(api_client, user, cookie):
    if cookie == "expired":
        api_client.cookies[COOKIE] = expired_token(user)
    elif cookie != "no cookie":
        api_client.cookies[COOKIE] = cookie

    response = refresh(api_client, **AJAX)

    assert response.status_code == 401
    assert "access" not in response.data
    assert COOKIE not in response.cookies


def test_refresh_without_the_header_is_rejected_and_the_token_is_kept(api_client, user):
    log_in(api_client)

    response = refresh(api_client)

    assert response.status_code == 403
    assert "access" not in response.data
    assert COOKIE not in response.cookies
    # The token was not spent: the same cookie still works with the header
    assert refresh(api_client, **AJAX).status_code == 200


def log_out(api, **extra):
    return api.post(reverse("accounts:token_blacklist"), **extra)


def assert_cookie_is_deleted(response):
    deleted = response.cookies[COOKIE]
    assert deleted.value == ""
    assert int(deleted["max-age"]) == 0
    assert deleted["path"] == "/api/v1/accounts/"


def test_logout_revokes_the_token_and_deletes_the_cookie(api_client, user):
    token = log_in(api_client).cookies[COOKIE].value

    response = log_out(api_client, **AJAX)

    assert response.status_code == 200
    assert_cookie_is_deleted(response)
    # Even someone who kept a copy of the token cannot use it any more
    api_client.cookies[COOKIE] = token
    assert refresh(api_client, **AJAX).status_code == 401


@pytest.mark.parametrize("cookie", ["no cookie", "not-a-token"])
def test_logout_always_deletes_the_cookie_and_answers_ok(api_client, user, cookie):
    if cookie != "no cookie":
        api_client.cookies[COOKIE] = cookie

    response = log_out(api_client, **AJAX)

    assert response.status_code == 200
    assert_cookie_is_deleted(response)


def test_logout_without_the_header_is_rejected_and_nothing_is_revoked(api_client, user):
    log_in(api_client)

    response = log_out(api_client)

    assert response.status_code == 403
    assert COOKIE not in response.cookies
    assert refresh(api_client, **AJAX).status_code == 200


def test_api_docs_describe_the_cookie_based_session():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]
    paths = schema["paths"]

    def body_properties(operation):
        ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        return set(components[ref.rsplit("/", 1)[1]]["properties"])

    login = paths["/api/v1/accounts/token/"]["post"]
    refresh = paths["/api/v1/accounts/token/refresh/"]["post"]
    logout = paths["/api/v1/accounts/token/blacklist/"]["post"]

    # The refresh token is in the cookie, so it is in no body the frontend would type
    assert body_properties(login) == {"access"}
    assert body_properties(refresh) == {"access"}
    assert "200" in logout["responses"]
    for operation in (refresh, logout):
        assert "requestBody" not in operation
        (header,) = [p for p in operation["parameters"] if p["name"] == "X-Requested-With"]
        assert header["in"] == "header"
        assert header["required"] is True


def test_the_cookie_is_always_secure_in_production():
    # Settings load once per process, so the production ones are loaded in a fresh one
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "x" * 50,
        "ALLOWED_HOSTS": "api.example.com",
        "DATABASE_URL": "postgres://u:p@localhost:5432/db",
        "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "WANPS_ENCRYPTION_KEY": "a-key-for-this-test",
        "AUTH_REFRESH_COOKIE_SECURE": "false",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; print(settings.AUTH_REFRESH_COOKIE_SECURE)",
        ],
        cwd=django_settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
