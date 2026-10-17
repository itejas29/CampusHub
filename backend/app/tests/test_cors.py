"""Cross-origin access is granted to exact origins, never to a whole hosting
platform. The API used to accept any *.vercel.app origin — and anyone can
deploy a site there."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

#: The pattern the Railway deployment sets — the project's own deployments only.
PROJECT_PATTERN = r"^https://campus-hub-fyb9(-[a-z0-9-]+)?\.vercel\.app$"


def _preflight(origin: str):
    return TestClient(app).options(
        "/api/v1/auth/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


def test_an_arbitrary_vercel_site_is_not_allowed_by_default():
    response = _preflight("https://someone-elses-app.vercel.app")
    assert "access-control-allow-origin" not in response.headers


def test_a_listed_development_origin_is_allowed():
    response = _preflight("http://localhost:5173")
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_the_deployment_pattern_admits_only_this_projects_urls():
    allowed = [
        "https://campus-hub-fyb9.vercel.app",
        "https://campus-hub-fyb9-nvx42xw74-itejas29s-projects.vercel.app",
        "https://campus-hub-fyb9-git-some-branch-itejas29s-projects.vercel.app",
    ]
    refused = [
        "https://evil.vercel.app",
        "https://xcampus-hub-fyb9.vercel.app",
        "https://campus-hub-fyb9.vercel.app.evil.com",
        "http://campus-hub-fyb9.vercel.app",
    ]
    assert all(re.fullmatch(PROJECT_PATTERN, o) for o in allowed)
    assert not any(re.fullmatch(PROJECT_PATTERN, o) for o in refused)
