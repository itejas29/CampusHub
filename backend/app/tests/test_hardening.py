"""Every response carries security headers; a NUL byte is refused, not a 500.

A `%00` in a search reached PostgreSQL, which refuses NUL in text, and six list
endpoints answered 500 (QA probe SEC-4). The API sent no security headers at
all — no `nosniff`, nothing against framing (SEC-6).
"""
from __future__ import annotations


def test_a_nul_byte_in_a_query_is_a_clean_400(api, world, login):
    response = api.get("/api/v1/students?q=%00", headers=login(world.admin.email))
    assert response.status_code == 400
    assert "invalid character" in response.json()["error"]["message"]


def test_responses_carry_security_headers(api, world, login):
    response = api.get("/api/v1/auth/me", headers=login(world.student_a.email))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_an_error_response_carries_them_too(api):
    response = api.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
