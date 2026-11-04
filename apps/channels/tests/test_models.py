"""
Tests for the channels models.
"""

import pytest
from django.db import IntegrityError, transaction
from wanps.messaging.models import App

from apps.channels.models import SharedMetaApp


def add_app(name):
    return App.objects.create(name=name, app_secret="app-secret", verify_token="verify-token")


def test_only_one_shared_meta_app_can_exist(db):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))

    with pytest.raises(IntegrityError), transaction.atomic():
        SharedMetaApp.objects.create(app=add_app("Another app"))

    assert SharedMetaApp.objects.count() == 1
