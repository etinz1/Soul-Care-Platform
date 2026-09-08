"""
Regression coverage for CORS: without it, every browser request from the
React frontend (a different origin than the API) is blocked by the browser
itself before it reaches any route — this was live in main.py for the
whole session until a real end-to-end browser check caught every dashboard
failing to load. This wasn't caught by earlier tests because they either
hit the app directly via ASGITransport with no Origin header (as most of
this suite still does) or, on the frontend side, mocked fetch entirely
(App.test.jsx) — neither path exercises actual browser CORS enforcement.
"""


async def test_allowed_frontend_origin_gets_cors_header(client):
    resp = await client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_unlisted_origin_does_not_get_cors_header(client):
    resp = await client.get("/healthz", headers={"Origin": "http://evil.example.com"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


async def test_preflight_request_is_allowed_for_frontend_origin(client):
    resp = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
