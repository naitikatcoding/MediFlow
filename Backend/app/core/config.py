from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    APP_NAME: str = "Stockout Shield"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "127.0.0.1"
    SECRET_KEY: str = "dev_secret_key_change_in_production_32chars_min_stockout_shield"
    
    # Database
    DATABASE_URL: str = "sqlite:///./stockout_shield.db"
    DB_ECHO: bool = False
    
    # External Integrations
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MEKO_API_KEY: Optional[str] = None
    MEKO_BASE_URL: str = "https://api.mekodata.ai/v1"
    
    # QR & Security
    QR_HMAC_SECRET: str = "dev_qr_hmac_secret_stockout_shield_token"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

