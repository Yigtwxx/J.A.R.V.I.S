from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Database
    database_url: str = "sqlite:///./data/jarvis.db"
    
    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    
    # Embedding & Vector Store
    embedding_model: str = "nomic-embed-text"
    chroma_db_path: str = "data/chroma_db"

    # GitHub
    github_token: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
