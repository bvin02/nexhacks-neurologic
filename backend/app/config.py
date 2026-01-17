"""
DecisionOS Configuration

Environment-based configuration with fail-fast validation.
API keys are required and must not be hardcoded.
"""
from typing import Literal
from pydantic_settings import BaseSettings
from pydantic import field_validator
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Provider Selection
    llm_provider: Literal["openai", "gemini"] = "gemini"
    
    # API Keys - Required based on provider
    openai_api_key: str = ""
    gemini_api_key: str = ""
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./decisionos.db"
    
    # Debug mode (verbose low-level logging)
    debug: bool = False
    
    # Follow-through mode (structured step-by-step execution tracing)
    follow_through: bool = False
    
    # Model configurations
    openai_heavy_model: str = "gpt-4o"
    openai_mid_model: str = "gpt-4o"
    openai_cheap_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    
    gemini_heavy_model: str = "gemini-2.5-pro"
    gemini_mid_model: str = "gemini-2.5-flash"
    gemini_cheap_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "models/text-embedding-004"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @field_validator("openai_api_key", "gemini_api_key", mode="before")
    @classmethod
    def validate_not_placeholder(cls, v: str) -> str:
        """Ensure API keys are not placeholder values."""
        if v and "your-" in v.lower():
            return ""
        return v
    
    def validate_provider_key(self) -> None:
        """Validate that the required API key for the selected provider is set."""
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required when LLM_PROVIDER=openai. "
                "Please set it in your .env file or environment."
            )
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is required when LLM_PROVIDER=gemini. "
                "Please set it in your .env file or environment."
            )
    
    def get_model(self, tier: Literal["cheap", "mid", "heavy"]) -> str:
        """Get the model name for the specified tier and current provider."""
        if self.llm_provider == "openai":
            return {
                "cheap": self.openai_cheap_model,
                "mid": self.openai_mid_model,
                "heavy": self.openai_heavy_model,
            }[tier]
        else:
            return {
                "cheap": self.gemini_cheap_model,
                "mid": self.gemini_mid_model,
                "heavy": self.gemini_heavy_model,
            }[tier]
    
    def get_embedding_model(self) -> str:
        """Get the embedding model for the current provider."""
        if self.llm_provider == "openai":
            return self.openai_embedding_model
        else:
            return self.gemini_embedding_model


# Global settings instance
settings = Settings()
