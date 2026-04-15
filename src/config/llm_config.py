"""Groq client factory and LLM constants."""
from groq import Groq

GENERATION_MODEL = "openai/gpt-oss-120b"
GENERATION_TEMPERATURE = 0.7
GENERATION_MAX_TOKENS = 2000

EXTRACTION_MODEL = "openai/gpt-oss-120b"
EXTRACTION_TEMPERATURE = 0.1
EXTRACTION_MAX_TOKENS = 1500


def create_groq_client(api_key: str) -> Groq:
    """Factory for Groq client u2014 replaceable for testing via monkeypatch."""
    return Groq(api_key=api_key)
