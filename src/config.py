from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field("gpt-4o-mini")
    openai_embedding_model: str = Field("text-embedding-3-small")
    tavily_api_key: str = Field(..., description="Tavily Search key")
    groq_api_key: str = Field(..., description="Groq API key")
    vector_store: str = Field("chroma")
    chroma_persist_dir: str = Field("/tmp/chroma")
    redis_url: str = Field("redis://localhost:6379")
    redis_ttl_seconds: int = Field(3600, ge=60)
    aws_region: str = Field("ap-south-1")
    s3_bucket_name: str = Field("it-support-docs")
    aws_access_key_id: str | None = Field(None)
    aws_secret_access_key: str | None = Field(None)
    postgres_url: str | None = Field(None)
    app_env: str = Field("development")
    log_level: str = Field("INFO")
    rate_limit: str = Field("10/minute")
    max_conversation_turns: int = Field(10, ge=1, le=50)
    retrieval_top_k: int = Field(4, ge=1, le=20)

    @field_validator("vector_store")
    @classmethod
    def validate_vector_store(cls, v: str) -> str:
        allowed = {"chroma", "pgvector"}
        if v not in allowed:
            raise ValueError(f"Must be one of {allowed}, got '{v}'")
        return v

    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "production", "testing"}
        if v not in allowed:
            raise ValueError(f"Must be one of {allowed}")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

settings = Settings()
