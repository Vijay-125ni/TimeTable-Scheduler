from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    USE_LOCAL_MONGODB: bool = False
    LOCAL_MONGODB_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "timetable_db"
    SECRET_KEY: str = "supersecretkey123"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 4320  # 3 days
    ALLOWED_ORIGINS: str = (
        "http://localhost:3002,http://localhost:3000,http://localhost:3003,http://localhost:5173"
    )
    SOLVER_TIME_LIMIT_SECONDS: int = 60
    AI_MODEL: str = "qwen-plus"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_TIMEOUT_SECONDS: int = 60
    DOCUMENT_UPLOAD_MAX_FILES: int = 10
    DOCUMENT_UPLOAD_MAX_FILE_BYTES: int = 15 * 1024 * 1024
    DOCUMENT_TEXT_MAX_CHARS: int = 200_000
    DOCUMENT_OCR_MAX_PAGES: int = 6
    DOCUMENT_ANALYSIS_MODEL: str = "qwen-plus"
    QWEN_API_KEY: Optional[str] = None
    DASHSCOPE_API_KEY: Optional[str] = None
    DOCUMENT_ANALYSIS_API_BASE: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    DOCUMENT_ANALYSIS_API_KEY: Optional[str] = None
    DOCUMENT_ANALYSIS_TIMEOUT_SECONDS: int = 120
    DOCUMENT_ANALYSIS_MAX_CHARS: int = 60_000

    @property
    def origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def active_mongodb_url(self) -> str:
        return self.LOCAL_MONGODB_URL if self.USE_LOCAL_MONGODB else self.MONGODB_URL

    @property
    def active_ai_api_key(self) -> Optional[str]:
        return self.QWEN_API_KEY or self.DASHSCOPE_API_KEY or self.OPENAI_API_KEY

    @property
    def active_ai_api_base(self) -> str:
        if self.QWEN_API_KEY or self.DASHSCOPE_API_KEY:
            return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        return self.OPENAI_API_BASE

    @property
    def active_ai_model(self) -> str:
        return self.DOCUMENT_ANALYSIS_MODEL or "qwen-plus"

    @property
    def active_document_analysis_model(self) -> str:
        if not self.DOCUMENT_ANALYSIS_MODEL or self.DOCUMENT_ANALYSIS_MODEL in ("qwen3:8b", "qwen2.5vl", "local"):
            return "qwen-plus"
        return self.DOCUMENT_ANALYSIS_MODEL

    @property
    def active_document_analysis_api_key(self) -> Optional[str]:
        key = self.QWEN_API_KEY or self.DASHSCOPE_API_KEY
        if key:
            return key
        if self.DOCUMENT_ANALYSIS_API_KEY and self.DOCUMENT_ANALYSIS_API_KEY != "local":
            return self.DOCUMENT_ANALYSIS_API_KEY
        return None

    @property
    def active_document_analysis_api_base(self) -> str:
        if not self.DOCUMENT_ANALYSIS_API_BASE or "localhost:11434" in self.DOCUMENT_ANALYSIS_API_BASE or "127.0.0.1:11434" in self.DOCUMENT_ANALYSIS_API_BASE:
            return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        return self.DOCUMENT_ANALYSIS_API_BASE

    class Config:
        env_file = BACKEND_DIR / ".env"
        extra = "ignore"


settings = Settings()

