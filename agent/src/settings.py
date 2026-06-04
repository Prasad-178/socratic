from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_model_fallback: str = "anthropic/claude-3.5-sonnet"
    embed_model: str = "openai/text-embedding-3-large"
    embed_dimensions: int = 1536
    database_url: str = "postgresql+psycopg://socratic:socratic@localhost:5432/socratic"
    langsmith_tracing: bool = True
    langsmith_project: str = "socratic"

settings = Settings()
