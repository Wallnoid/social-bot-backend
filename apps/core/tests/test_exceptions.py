"""
Tests for the format of API errors.
"""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_token_errors_have_a_plain_message_and_code():
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-token")

    response = api.get("/api/v1/accounts/users/me/")

    assert response.status_code == 401
    assert response.data["code"] == "token_not_valid"
    assert response.data["message"] == "Given token not valid for any token type"


@pytest.mark.django_db
def test_other_errors_keep_their_code():
    response = APIClient().get("/api/v1/accounts/users/me/")

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"
    assert response.data["message"] == "Authentication credentials were not provided."
