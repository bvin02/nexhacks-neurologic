"""
OpenAI LLM Provider

Implementation using OpenAI's Chat Completions and Embeddings APIs.
"""
from typing import Optional
import logging

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import LLMProvider, LLMError, LLMRateLimitError
from ..config import settings

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """
    OpenAI API implementation.
    
    Supports:
    - gpt-4o for heavy reasoning
    - gpt-4o-mini for cheap routing/extraction
    - text-embedding-3-small for embeddings
    """
    
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def generate_text(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate text using OpenAI Chat Completions API."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            
            return response.choices[0].message.content or ""
            
        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise LLMRateLimitError(f"OpenAI rate limit: {e}")
            raise LLMError(f"OpenAI error: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def embed_text(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]:
        """Generate embeddings using OpenAI Embeddings API."""
        try:
            # Batch texts (OpenAI supports batching)
            response = await self.client.embeddings.create(
                model=model,
                input=texts,
            )
            
            return [item.embedding for item in response.data]
            
        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise LLMRateLimitError(f"OpenAI rate limit: {e}")
            raise LLMError(f"OpenAI embedding error: {e}")
