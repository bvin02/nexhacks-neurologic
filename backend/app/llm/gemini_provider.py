"""
Google Gemini LLM Provider

Implementation using Google's Generative AI SDK.
"""
from typing import Optional
import logging

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import LLMProvider, LLMError, LLMRateLimitError
from ..config import settings

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    Google Gemini API implementation.
    
    model supports in config.py
    """
    
    def __init__(self):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for Gemini provider")
        genai.configure(api_key=settings.gemini_api_key)
    
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
        """Generate text using Gemini Generative API."""
        try:
            gen_model = genai.GenerativeModel(model_name=model)
            
            generation_config = genai.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            
            # Prepend system prompt to user prompt if provided
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
            
            response = await gen_model.generate_content_async(
                full_prompt,
                generation_config=generation_config,
            )
            
            return response.text or ""
            
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                raise LLMRateLimitError(f"Gemini rate limit: {e}")
            raise LLMError(f"Gemini error: {e}")
    
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
        """Generate embeddings using Gemini Embeddings API."""
        import asyncio
        
        logger.debug(f"embed_text called with {len(texts)} texts, model={model}")
        
        def _embed_batch_sync() -> list[list[float]]:
            """Synchronous embedding for all texts - runs in thread."""
            results = []
            for i, text in enumerate(texts):
                logger.debug(f"Embedding text {i+1}/{len(texts)}")
                result = genai.embed_content(
                    model=model,
                    content=text,
                    task_type="retrieval_document",
                )
                results.append(result["embedding"])
            return results
        
        try:
            # Run the sync embedding function in a thread to avoid blocking
            embeddings = await asyncio.to_thread(_embed_batch_sync)
            logger.debug(f"embed_text completed with {len(embeddings)} embeddings")
            return embeddings
            
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                raise LLMRateLimitError(f"Gemini rate limit: {e}")
            raise LLMError(f"Gemini embedding error: {e}")


