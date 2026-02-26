from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/jarvis"
    
    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    
    # GitHub
    github_token: str = ""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
