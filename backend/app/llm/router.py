"""
LLM Router

Model tier routing and provider factory.
Decides which model to use based on task complexity.
"""
from enum import Enum
from typing import Optional
import logging

from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from ..config import settings

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Model tiers based on cost and capability."""
    CHEAP = "cheap"   # Intent routing, extraction, dedup
    MID = "mid"       # Standard responses, planning
    HEAVY = "heavy"   # Enforcement, deep synthesis


# Singleton provider instance
_provider_instance: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """
    Get or create the LLM provider instance.
    
    Provider is selected based on LLM_PROVIDER environment variable.
    Uses singleton pattern to reuse connections.
    """
    global _provider_instance
    
    if _provider_instance is None:
        settings.validate_provider_key()
        
        if settings.llm_provider == "openai":
            logger.info("Initializing OpenAI provider")
            _provider_instance = OpenAIProvider()
        elif settings.llm_provider == "gemini":
            logger.info("Initializing Gemini provider")
            _provider_instance = GeminiProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
    
    return _provider_instance


def get_model_for_tier(tier: ModelTier) -> str:
    """
    Get the model name for a given tier.
    
    Uses configured models based on provider.
    """
    return settings.get_model(tier.value)


def get_embedding_model() -> str:
    """Get the embedding model for the current provider."""
    return settings.get_embedding_model()


# Task to tier mapping
TASK_TIERS = {
    # Cheap tier tasks
    "intent_routing": ModelTier.CHEAP,
    "memory_extraction": ModelTier.CHEAP,
    "deduplication": ModelTier.CHEAP,
    "conflict_classification": ModelTier.CHEAP,
    "summarization": ModelTier.CHEAP,
    
    # Mid tier tasks
    "standard_response": ModelTier.MID,
    "planning": ModelTier.MID,
    "explanation": ModelTier.MID,
    
    # Heavy tier tasks
    "enforcement_reasoning": ModelTier.HEAVY,
    "contradiction_resolution": ModelTier.HEAVY,
    "deep_synthesis": ModelTier.HEAVY,
}


def get_tier_for_task(task: str) -> ModelTier:
    """Get the appropriate tier for a given task."""
    return TASK_TIERS.get(task, ModelTier.MID)


def get_model_for_task(task: str) -> str:
    """Get the model name for a given task."""
    tier = get_tier_for_task(task)
    return get_model_for_tier(tier)
