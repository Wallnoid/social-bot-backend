"""
A fake Meta for development.

While it is installed, the messages that `wanps-core` sends to Meta's Graph API are answered
here, as Meta would answer a success, so the inbox can be tried with fake accounts. Any text
with `#fail` is answered as a rejection, to see how the frontend shows a delivery error.
Calls to any other address still reach the real `requests.post`.
"""

import json as _json
import logging
import uuid
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

GRAPH_HOSTS = {"graph.facebook.com", "graph.instagram.com"}
FAIL_MARKER = "#fail"

_real_post = None


def _answer(status_code, body):
    response = requests.Response()
    response.status_code = status_code
    response._content = _json.dumps(body).encode()
    return response


def _is_a_send(url):
    """Only the sending addresses are faked (`.../messages`); anything else is not ours to answer."""
    parsed = urlparse(url)
    return parsed.hostname in GRAPH_HOSTS and parsed.path.endswith("/messages")


def _fake_post(url, data=None, json=None, **kwargs):
    if not _is_a_send(url):
        return _real_post(url, data=data, json=json, **kwargs)
    payload = json or {}
    if FAIL_MARKER in _json.dumps(payload):
        return _answer(400, {"error": {"message": "Forced failure (#fail)", "code": 100}})
    if payload.get("messaging_product") == "whatsapp":
        return _answer(
            200,
            {
                "messaging_product": "whatsapp",
                "messages": [{"id": f"wamid.fake.{uuid.uuid4().hex}"}],
            },
        )
    return _answer(200, {"message_id": f"mid.fake.{uuid.uuid4().hex}"})


def install():
    global _real_post
    if _real_post is None:
        _real_post = requests.post
        requests.post = _fake_post
        logger.warning("META_FAKE is on: the messages sent to Meta are NOT really sent.")


def uninstall():
    global _real_post
    if _real_post is not None:
        requests.post = _real_post
        _real_post = None
