"""OpenAI-compatible client factory, provider registry, and LLM constants."""
import os

from openai import OpenAI

# --- Provider registry ---
PROVIDER_URLS: dict[str, str] = {
    "9router":    os.getenv("NINER_ROUTER_URL", "http://localhost:20128/v1"),
    "groq":       "https://api.groq.com/openai/v1",
    "openai":     "https://api.openai.com/v1",
    "minimax":    "https://api.minimax.chat/v1",
    "together":   "https://api.together.xyz/v1",
    "fireworks":  "https://api.fireworks.ai/inference/v1",
    "deepseek":   "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

# Env-level defaults
_API_KEY_ENV: str = os.getenv("API_KEY", "")
BASE_URL: str = os.getenv("BASE_URL", PROVIDER_URLS["groq"])

# Models — read from env, with sensible fallbacks
GENERATION_MODEL: str = os.getenv("GENERATION_MODEL", "openai/gpt-oss-120b")
GENERATION_TEMPERATURE: float = float(os.getenv("GENERATION_TEMPERATURE", "0.7"))
GENERATION_MAX_TOKENS: int = int(os.getenv("GENERATION_MAX_TOKENS", "3000"))

EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", "openai/gpt-oss-120b")
EXTRACTION_TEMPERATURE: float = float(os.getenv("EXTRACTION_TEMPERATURE", "0.1"))
EXTRACTION_MAX_TOKENS: int = int(os.getenv("EXTRACTION_MAX_TOKENS", "1500"))


def resolve_base_url(provider: str, custom_url: str = "") -> str:
    """Return the base URL for the given provider name.

    'custom' uses custom_url if provided, else falls back to BASE_URL env var.
    Unknown provider names also fall back to BASE_URL.
    """
    if provider == "custom":
        return custom_url or BASE_URL
    return PROVIDER_URLS.get(provider, BASE_URL)


def create_client(api_key: str = "", base_url: str = "") -> OpenAI:
    """Factory for any OpenAI-compatible client.

    Falls back to API_KEY / BASE_URL env vars when arguments are empty.
    """
    key = api_key or _API_KEY_ENV
    url = base_url or BASE_URL
    return OpenAI(api_key=key, base_url=url)
