"""
The OpenAPI schema the frontend generates its types from.
"""

import json


def test_the_schema_is_served_as_json_at_openapi_json(client):
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi+json")
    schema = json.loads(response.content)
    assert schema["openapi"].startswith("3.")
    assert "/api/v1/inbox/{channel}/conversations/" in schema["paths"]


def test_the_schema_is_still_served_at_api_schema(client):
    response = client.get("/api/schema/")

    assert response.status_code == 200
