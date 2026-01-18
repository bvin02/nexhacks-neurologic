"""
Token Compression Service

Integrates with The Token Company API to compress prompts
before LLM invocation, reducing token usage and costs.
"""
import logging
import httpx
from typing import Optional
from dataclasses import dataclass

from ..config import settings
from ..tracer import trace_section, trace_input, trace_step, trace_call, trace_result, trace_output

logger = logging.getLogger(__name__)


def _debug_print(msg: str, data: any = None):
    """Print debug message for token compression - always visible."""
    prefix = "\n🔧 [TOKEN_COMPRESSION]"
    if data is not None:
        print(f"{prefix} {msg}: {data}")
    else:
        print(f"{prefix} {msg}")


@dataclass
class CompressionResult:
    """Result of token compression."""
    output: str
    original_tokens: int
    compressed_tokens: int
    tokens_saved: int
    compression_time: float
    compression_ratio: float


class TokenCompressionService:
    """
    Service for compressing text using The Token Company API.
    
    Uses the bear-1 model with configurable aggressiveness.
    """
    
    API_URL = "https://api.thetokencompany.com/v1/compress"
    DEFAULT_AGGRESSIVENESS = 0.5  # Moderate - good balance
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.token_company_api_key
        if not self.api_key:
            logger.warning("Token Company API key not configured")
    
    async def compress(
        self,
        text: str,
        aggressiveness: float = DEFAULT_AGGRESSIVENESS,
        max_output_tokens: Optional[int] = None,
        min_output_tokens: Optional[int] = None,
    ) -> CompressionResult:
        """
        Compress text using Token Company API.
        
        Args:
            text: The text to compress
            aggressiveness: How aggressively to compress (0.0-1.0)
            max_output_tokens: Optional max tokens in output
            min_output_tokens: Optional min tokens in output
            
        Returns:
            CompressionResult with compressed text and metrics
        """
        print("\n" + "=" * 60)
        print("🚀 TOKEN COMPRESSION SERVICE CALLED")
        print("=" * 60)
        _debug_print("Input text length (chars)", len(text))
        _debug_print("Aggressiveness level", aggressiveness)
        _debug_print("API URL", self.API_URL)
        _debug_print("API Key configured", "Yes" if self.api_key else "NO - MISSING!")
        
        trace_section("Token Compression")
        trace_input("token_compression", "text_length", len(text))
        trace_input("token_compression", "aggressiveness", aggressiveness)
        
        if not self.api_key:
            _debug_print("❌ ERROR: No API key configured - returning original text")
            trace_result("token_compression", "compress", False, "No API key configured")
            # Return original text with dummy metrics
            return CompressionResult(
                output=text,
                original_tokens=len(text) // 4,  # Rough estimate
                compressed_tokens=len(text) // 4,
                tokens_saved=0,
                compression_time=0,
                compression_ratio=1.0,
            )
        
        _debug_print("Building API payload...")
        trace_step("token_compression", "Calling Token Company API")
        
        payload = {
            "model": "bear-1",
            "compression_settings": {
                "aggressiveness": aggressiveness,
                "max_output_tokens": max_output_tokens,
                "min_output_tokens": min_output_tokens,
            },
            "input": text,
        }
        
        _debug_print("Payload model", payload["model"])
        _debug_print("Payload settings", payload["compression_settings"])
        _debug_print("Input preview (first 200 chars)", text[:200] + "..." if len(text) > 200 else text)
        
        trace_call("token_compression", "api.compress", f"aggressiveness={aggressiveness}")
        
        print("\n📡 Making HTTP POST request to Token Company...")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                _debug_print("Sending request with timeout", "30.0 seconds")
                response = await client.post(
                    self.API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json=payload,
                )
                _debug_print("Response status code", response.status_code)
                response.raise_for_status()
                data = response.json()
            
            print("\n✅ API RESPONSE RECEIVED:")
            _debug_print("Raw response keys", list(data.keys()))
            
            original_tokens = data.get("original_input_tokens", 0)
            compressed_tokens = data.get("output_tokens", 0)
            tokens_saved = original_tokens - compressed_tokens
            compression_ratio = original_tokens / compressed_tokens if compressed_tokens > 0 else 1.0
            
            print("\n📊 COMPRESSION RESULTS:")
            _debug_print("Original tokens", original_tokens)
            _debug_print("Compressed tokens", compressed_tokens)
            _debug_print("Tokens SAVED", f"{tokens_saved} ({(tokens_saved/original_tokens*100):.1f}% reduction)" if original_tokens > 0 else "N/A")
            _debug_print("Compression ratio", f"{compression_ratio:.2f}x")
            _debug_print("Compression time (s)", data.get("compression_time", 0))
            
            compressed_output = data.get("output", text)
            _debug_print("Output preview (first 200 chars)", compressed_output[:200] + "..." if len(compressed_output) > 200 else compressed_output)
            
            result = CompressionResult(
                output=compressed_output,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                tokens_saved=tokens_saved,
                compression_time=data.get("compression_time", 0),
                compression_ratio=compression_ratio,
            )
            
            trace_result("token_compression", "api.compress", True, 
                        f"{original_tokens} -> {compressed_tokens} tokens ({tokens_saved} saved)")
            trace_output("token_compression", "compression_ratio", f"{compression_ratio:.2f}x")
            
            print("=" * 60)
            print(f"✅ COMPRESSION COMPLETE: {original_tokens} → {compressed_tokens} tokens ({tokens_saved} saved)")
            print("=" * 60 + "\n")
            
            return result
            
        except httpx.HTTPStatusError as e:
            print("\n❌ HTTP ERROR FROM TOKEN COMPANY API:")
            _debug_print("Status code", e.response.status_code)
            _debug_print("Response body", e.response.text[:500] if e.response.text else "Empty")
            logger.error(f"Token Company API error: {e.response.status_code} - {e.response.text}")
            trace_result("token_compression", "api.compress", False, f"HTTP {e.response.status_code}")
            print("=" * 60 + "\n")
            # Return original text on error
            return CompressionResult(
                output=text,
                original_tokens=len(text) // 4,
                compressed_tokens=len(text) // 4,
                tokens_saved=0,
                compression_time=0,
                compression_ratio=1.0,
            )
        except Exception as e:
            print("\n❌ UNEXPECTED ERROR IN TOKEN COMPRESSION:")
            _debug_print("Exception type", type(e).__name__)
            _debug_print("Exception message", str(e))
            logger.error(f"Token compression failed: {e}")
            trace_result("token_compression", "api.compress", False, str(e))
            print("=" * 60 + "\n")
            # Return original text on error
            return CompressionResult(
                output=text,
                original_tokens=len(text) // 4,
                compressed_tokens=len(text) // 4,
                tokens_saved=0,
                compression_time=0,
                compression_ratio=1.0,
            )


# Singleton instance
_token_compression_service: Optional[TokenCompressionService] = None


def get_token_compression_service() -> TokenCompressionService:
    """Get the singleton token compression service instance."""
    global _token_compression_service
    if _token_compression_service is None:
        _token_compression_service = TokenCompressionService()
    return _token_compression_service
