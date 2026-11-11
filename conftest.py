"""
Shared pytest setup.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def load_wanps_whatsapp_modules():
    """
    Import the WhatsApp modules of `wanps-core` before any test runs.

    They are imported lazily, with the first webhook request, and bind
    `handle_message` at that moment. A test that patches
    `wanps.messaging.dispatch.handle_message` and sends the first webhook would make them
    keep the mock for the rest of the session, so later tests would stop reaching the bot.
    """
    import wanps.whatsapp.tasks  # noqa: F401
    import wanps.whatsapp.views  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def meta_is_not_faked_unless_a_test_asks():
    """
    Turn the fake Meta off before any test runs.

    A developer who has META_FAKE=true in .env to try the frontend starts Django with the fake
    already installed; the tests must run the same for them as for everyone else. The tests of
    the fake install it themselves.
    """
    from apps.devtools import fake_meta

    fake_meta.uninstall()


@pytest.fixture(autouse=True)
def events_of_the_inbox_stay_in_memory(settings):
    """
    Deliver the events of the inbox in memory in every test.

    A message saved for a connected account announces itself through the channel layer; the
    tests must not reach the Redis of a developer who has it running.
    """
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    settings.CACHES = {
        **settings.CACHES,
        "ws_tickets": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ws-tickets-of-the-tests",
        },
    }


@pytest.fixture(autouse=True)
def throttle_counters_start_from_zero():
    """Rate limit counters live in the cache; every test starts with none."""
    from django.core.cache import cache

    cache.clear()
