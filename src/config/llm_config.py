"""OpenAI-compatible client factory and LLM constants."""
import os

from openai import OpenAI

BASE_URL: str = os.getenv("BASE_URL", "https://api.groq.com/openai/v1")
_API_KEY_ENV: str = os.getenv("API_KEY", "")

GENERATION_MODEL = "openai/gpt-oss-120b"
GENERATION_TEMPERATURE = 0.7
GENERATION_MAX_TOKENS = 2000

EXTRACTION_MODEL = "openai/gpt-oss-120b"
EXTRACTION_TEMPERATURE = 0.1
EXTRACTION_MAX_TOKENS = 1500


def create_client(api_key: str = "") -> OpenAI:
    """Factory for OpenAI-compatible client. Falls back to API_KEY env var."""
    key = api_key or _API_KEY_ENV
    return OpenAI(api_key=key, base_url=BASE_URL)
