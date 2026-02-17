"""Pydantic settings: config/config.yml (defaults) and .env (override)."""

import os
from pathlib import Path

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from pydantic_settings.sources import InitSettingsSource


def _strip_quotes(v: str) -> str:
    if not isinstance(v, str):
        return v
    return v.strip().strip('"').strip("'").strip()


def _load_yaml_config() -> dict:
    """Load config/config.yml and flatten to Settings field names. Missing file -> {}."""
    base = Path(__file__).resolve().parent.parent
    path = base / os.environ.get("CONFIG_FILE", "config/config.yml")
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    app = data.get("app") or {}
    server = data.get("server") or {}
    chroma = data.get("chroma") or {}
    langsmith = data.get("langsmith") or {}
    flat: dict = {}
    if app.get("openai_model") is not None:
        flat["openai_model"] = app["openai_model"]
    if app.get("embedding_model") is not None:
        flat["embedding_model"] = app["embedding_model"]
    if app.get("max_iterations") is not None:
        flat["max_iterations"] = app["max_iterations"]
    if app.get("max_sources_used") is not None:
        flat["max_sources_used"] = app["max_sources_used"]
    if server.get("cors_origins") is not None:
        flat["cors_origins"] = server["cors_origins"]
    if chroma.get("persist_directory") is not None:
        flat["chroma_persist_directory"] = chroma["persist_directory"]
    if chroma.get("http_port") is not None:
        flat["chroma_http_port"] = chroma["http_port"]
    if langsmith.get("project") is not None:
        flat["langsmith_project"] = langsmith["project"]
    if langsmith.get("endpoint") is not None:
        flat["langsmith_endpoint"] = langsmith["endpoint"]
    return flat


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    tavily_api_key: str = ""
    serpapi_api_key: str = ""
    chroma_persist_directory: str = "./chroma_db"
    chroma_http_host: str = ""
    chroma_http_port: int = 8000
    database_url: str = ""
    redis_url: str = ""
    max_iterations: int = 3
    max_sources_used: int = 10
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "research-synthesis-agent"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_workspace_id: str = ""

    @field_validator(
        "langsmith_project",
        "langsmith_endpoint",
        "langsmith_workspace_id",
        mode="before",
    )
    @classmethod
    def strip_langsmith_strings(cls, v: str | None) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return _strip_quotes(v) or ""
        return ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority: env > dotenv > init > config.yml (so .env overrides config.yml)
        yaml_source = InitSettingsSource(settings_cls, _load_yaml_config())
        return (env_settings, dotenv_settings, init_settings, yaml_source)


settings = Settings()
