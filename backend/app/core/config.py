"""Application settings, loaded from environment (12-factor)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    PROJECT_NAME: str = "CampusHub"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- database -----------------------------------------------------------
    POSTGRES_USER: str = "campushub"
    POSTGRES_PASSWORD: str = "campushub_dev_password"
    POSTGRES_DB: str = "campushub"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # --- auth ---------------------------------------------------------------
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # Comma-separated in .env; parsed by the `cors_origins` property below.
    # Kept as a plain string so pydantic-settings does not attempt JSON decoding.
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    #: Optional pattern for origins that cannot be listed exactly — Vercel gives
    #: every preview deployment its own URL. Anchor it to the project, e.g.
    #: ^https://campus-hub-fyb9(-[a-z0-9-]+)?\.vercel\.app$ — never a bare
    #: *.vercel.app, which any Vercel user can deploy to.
    BACKEND_CORS_ORIGIN_REGEX: str = ""

    # --- storage ------------------------------------------------------------
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_DIR: str = "./uploads"
    LOCAL_STORAGE_PUBLIC_URL: str = "/media"
    MAX_UPLOAD_SIZE_MB: int = 15

    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = ""
    S3_PUBLIC_BASE_URL: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    SEED_DEFAULT_PASSWORD: str = "Campus@123"

    #: How a Minor coordinator's department scope is read — see
    #: `services/scope.MinorScopeRule`. "OFFERING" limits them to the minors
    #: their department offers; "APPLICANT" to applications from their own
    #: students; "EITHER" accepts both. Left at EITHER until the university
    #: confirms which rule applies, so the choice stays a policy decision rather
    #: than an assumption baked into the code.
    MINOR_COORDINATOR_SCOPE: str = "EITHER"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
