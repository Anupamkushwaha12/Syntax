from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_SECRET_KEY: str = "dev-secret-key"
    APP_ENV: str = "development"
    FRONTEND_URL: str = "http://localhost:5500"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/foodbridge"
    SYNC_DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/foodbridge"

    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET_KEY: str = "dev-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"

    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 5

    VOLUNTEER_RESPONSE_TIMEOUT_MINUTES: int = 5
    MAX_MATCHING_RADIUS_KM: float = 20.0
    AVG_SPEED_KMH: float = 30.0

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
