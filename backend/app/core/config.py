"""应用配置。

所有配置项经 pydantic-settings 从环境变量 / .env 读取，
代码中不存在任何硬编码密钥。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    APP_ENV: str = "development"
    APP_NAME: str = "秋招 AI 面试陪练平台"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me-to-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ---- 数据库 ----
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # ---- LLM ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
    LLM_MODEL_EVAL: str = ""
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 2
    # 强制指定 provider：auto | openai | mock。auto = 有 key 走 openai，无 key 走 mock
    LLM_PROVIDER: str = "auto"

    # ---- 上传 ----
    UPLOAD_MAX_MB: int = 5

    # ---- CORS ----
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ------------------------------------------------------------------
    # 派生属性
    # ------------------------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def eval_model(self) -> str:
        """评分/报告使用的模型（未单独配置时复用主模型）。"""
        return self.LLM_MODEL_EVAL or self.LLM_MODEL

    @property
    def upload_max_bytes(self) -> int:
        return self.UPLOAD_MAX_MB * 1024 * 1024

    @property
    def is_mock_llm(self) -> bool:
        """是否使用内置 Mock 面试官。"""
        if self.LLM_PROVIDER == "mock":
            return True
        if self.LLM_PROVIDER == "openai":
            return False
        # auto：没有 key 就降级为 mock
        return not self.LLM_API_KEY.strip()

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
