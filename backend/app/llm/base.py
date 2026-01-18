"""
LLM Provider Base Class

Abstract interface that all LLM providers must implement.
Includes retry logic, schema validation, and error handling.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
import json
import logging

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""
    pass


class LLMInvalidResponseError(LLMError):
    """Invalid response from LLM."""
    pass


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All LLM calls go through this interface, allowing
    provider switching without changing system logic.
    """
    
    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate text from a prompt.
        
        Args:
            prompt: The user prompt
            model: Model name to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            
        Returns:
            Generated text
        """
        pass
    
    @abstractmethod
    async def embed_text(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]:
        """
        Generate embeddings for texts.
        
        Args:
            texts: List of texts to embed
            model: Embedding model to use
            
        Returns:
            List of embedding vectors
        """
        pass
    
    async def extract_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """
        Extract structured JSON from a prompt.
        
        Uses retry logic to handle invalid JSON responses.
        Validates against the provided Pydantic schema.
        
        Args:
            prompt: The user prompt
            schema: Pydantic model to validate against
            model: Model name to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (lower for structured output)
            system_prompt: Optional system prompt
            max_retries: Number of retries for invalid JSON
            
        Returns:
            Validated dictionary matching the schema
        """
        json_system = (system_prompt or "") + """

You must respond with valid JSON only. No markdown, no explanations.
The JSON must match this schema:
""" + json.dumps(schema.model_json_schema(), indent=2)
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = await self.generate_text(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_prompt=json_system,
                )
                
                # Clean response - remove markdown code blocks if present
                cleaned = response.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                
                # Parse JSON
                parsed = json.loads(cleaned)
                
                # Validate against schema
                validated = schema.model_validate(parsed)
                return validated.model_dump()
                
            except json.JSONDecodeError as e:
                last_error = LLMInvalidResponseError(f"Invalid JSON: {e}")
                logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
                continue
                
            except ValidationError as e:
                last_error = LLMInvalidResponseError(f"Schema validation failed: {e}")
                logger.warning(f"Schema validation error on attempt {attempt + 1}: {e}")
                continue
        
        raise last_error or LLMInvalidResponseError("Failed to extract valid JSON")
    
    @staticmethod
    def create_retry_decorator(max_attempts: int = 3):
        """Create a retry decorator for API calls."""
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((Exception,)),
            reraise=True,
        )
