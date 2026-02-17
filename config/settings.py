"""Pydantic settings loaded from .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""
    serpapi_api_key: str = ""
    chroma_persist_directory: str = "./chroma_db"
    database_url: str = ""
    redis_url: str = ""
    max_iterations: int = 3
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "research-synthesis-agent"
    langsmith_workspace_id: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
