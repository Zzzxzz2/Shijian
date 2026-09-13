import os

ENVIRONMENT: str = os.getenv("ENV", "development").lower()
_jwt_secret = os.getenv("JWT_SECRET")
if ENVIRONMENT == "production" and (
    not _jwt_secret or len(_jwt_secret.strip()) < 32
    or _jwt_secret == "shijian-dev-secret-key-change-in-production"
    or _jwt_secret.lower().startswith(("replace-", "change-me", "changeme"))
):
    raise RuntimeError("JWT_SECRET must be a unique secret of at least 32 characters when ENV=production")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./shijian.db",
)

JWT_SECRET: str = _jwt_secret or "shijian-dev-secret-key-change-in-production"

JWT_ALGORITHM: str = "HS256"
JWT_EXPIRATION_HOURS: int = 24
