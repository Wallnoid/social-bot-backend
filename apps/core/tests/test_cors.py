"""
What a browser on another origin is allowed to send to the API.
"""

import pytest

ORIGIN = "http://localhost:5173"


@pytest.mark.parametrize(
    "header", ["authorization", "content-type", "x-tenant-id", "x-requested-with"]
)
def test_a_browser_may_send_the_headers_the_app_uses(client, header):
    # The preflight a browser makes before a cross-origin request with that header
    response = client.options(
        "/api/v1/tenants/current/",
        HTTP_ORIGIN=ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS=header,
    )

    assert response.status_code == 200
    assert header in response["Access-Control-Allow-Headers"].lower()
    assert response["Access-Control-Allow-Credentials"] == "true"
