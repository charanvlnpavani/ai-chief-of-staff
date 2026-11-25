"""Health checks, error format, security headers and request ids."""

from httpx import AsyncClient


async def test_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_security_headers_and_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/config")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers["x-request-id"]) >= 8


async def test_incoming_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"x-request-id": "trace-abc-12345"})
    assert response.headers["x-request-id"] == "trace-abc-12345"


async def test_unknown_route_returns_problem_json(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "not_found"
    assert body["status"] == 404
    assert body["instance"] == "/api/v1/does-not-exist"


async def test_validation_errors_do_not_echo_input(owner: AsyncClient) -> None:
    secret_looking = "Bearer sk-should-not-echo"
    response = await owner.patch("/api/v1/users/me", json={"timezone": secret_looking})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert secret_looking not in response.text
    assert body["errors"][0]["loc"][-1] == "timezone"


async def test_auth_config_reports_available_methods(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/config")
    assert response.json() == {"googleEnabled": True, "devLoginEnabled": True}
