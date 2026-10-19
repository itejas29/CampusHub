from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.hardening import HardeningMiddleware

DESCRIPTION = """
CampusHub — PDEU centralised student portal.

**Phase 1** delivers the foundation: authentication, RBAC, a configuration-driven
curriculum, elective/MOOC/minor skeletons, a reusable internship engine (CSSI and
Summer Internship), clubs and events, mentorship, notifications, file storage and
an audit trail.

Institutional business rules — elective allocation formulas, merit weighting and
grade boundaries — are intentionally **not** implemented; they plug into
`app/services/allocation` once the department confirms them.
"""

# The interactive docs publish every route and schema; useful in development,
# not something to hand the internet in production.
_DOCS = settings.ENVIRONMENT != "production"

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=DESCRIPTION,
    version="1.0.0-phase1",
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Was any *.vercel.app site — anyone can deploy one. Now opt-in and exact
    # to this project's deployments (see BACKEND_CORS_ORIGIN_REGEX).
    allow_origin_regex=settings.BACKEND_CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Outermost: security headers on every response, CORS ones included.
app.add_middleware(HardeningMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Uploads are NOT mounted as static files.
#
# They used to be, and it meant every stored document — internship certificates,
# offer letters, weekly reports — was readable by anyone who knew or guessed its
# object key, with no login at all. Uploads now reach clients only through
# `GET /api/v1/files/{id}/download`, which authorises the caller (or verifies a
# short-lived signed token) before streaming a byte.
#
# The directory is still created so the local backend has somewhere to write.
if settings.STORAGE_BACKEND == "local":
    Path(settings.LOCAL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "environment": settings.ENVIRONMENT,
            "version": app.version}


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": settings.PROJECT_NAME, "docs": "/docs",
            "api": settings.API_V1_PREFIX}
