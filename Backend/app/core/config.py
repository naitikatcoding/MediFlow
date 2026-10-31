from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """MediFlow Central Application Configuration with Environment Validation."""
    
    # Core Application
    APP_NAME: str = "MediFlow"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "127.0.0.1"
    
    # Base URLs
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://127.0.0.1:8000"
    
    # Security & Auth Secrets (dev defaults with placeholders)
    SECRET_KEY: str = "dev_secret_key_change_in_production_32chars_min_mediflow"
    AUTH_SECRET: str = "dev_auth_secret_token_change_in_production"
    AUTH_ISSUER: str = "mediflow-auth"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    # Operational Database (YugabyteDB / PostgreSQL with SQLite local fallback)
    DATABASE_URL: str = "sqlite:///./mediflow.db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(default=2, ge=1, le=2)
    DB_MAX_OVERFLOW: int = Field(default=1, ge=0, le=1)
    DB_SQLITE_FALLBACK: Optional[bool] = None
    
    # External AI: Google Gemini
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # External AI: MEKO Shared Memory & Decision Traces
    MEKO_API_KEY: Optional[str] = None
    MEKO_BASE_URL: str = "https://api.mekodata.ai/v1"
    MEKO_MCP_URL: Optional[str] = None
    MEKO_DATAPACK_ID: Optional[str] = None
    
    # QR & Physical Handoff Security
    QR_HMAC_SECRET: str = "dev_qr_hmac_secret_mediflow_token"
    
    # CORS Allowed Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        return ["*"]

    @property
    def is_yugabyte(self) -> bool:
        """Indicate whether the active database is PostgreSQL/YugabyteDB."""
        return "postgresql" in self.DATABASE_URL or "yugabyte" in self.DATABASE_URL

    @property
    def allow_sqlite_fallback(self) -> bool:
        """Enable local fallback by default outside production."""
        if self.DB_SQLITE_FALLBACK is not None:
            return self.DB_SQLITE_FALLBACK
        return self.APP_ENV.lower() != "production"

    @property
    def is_gemini_active(self) -> bool:
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY != "your_gemini_api_key_here")

    @property
    def is_meko_active(self) -> bool:
        return bool(self.MEKO_API_KEY and self.MEKO_API_KEY != "your_meko_api_key_here")


settings = Settings()
