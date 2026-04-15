"""PersonaGenerator: validates persona name and calls LLM to generate a FullPayload."""
from __future__ import annotations

import json

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import FullPayload
from src.config.llm_config import (
    GENERATION_MAX_TOKENS,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    create_client,
)
from src.generator.prompts.generation_prompt import GENERATION_SYSTEM_PROMPT

VALID_PERSONAS = [
    "Veteran Lead", "Senior worker", "Family-First Parent",
    "Caregiver of aging parents", "Religious catholic worker",
    "Part-Time Student", "Night Owl", "Early Bird", "Weekend Warrior",
    "Cranky Old-Timer", "Pair bonded", "Injury-Returning Worker",
    "New Hire (Probationary)", "Safety Champion", "Regional Road Warrior",
    "Master Packer", "Night School Student", "Volunteer", "Gym Fanatic",
    "Injury-Returning (Back)", "Injury-Returning (Knee)",
    "Diabetic (Meal Timing)", "Chronic Fatigue", "Allergy-Restricted",
    "Eager Rookie", "Summer Help", "Apprentice",
]


class InvalidPersonaError(ValueError):
    pass


class GenerationError(RuntimeError):
    pass


class PersonaGenerator:
    def validate_persona(self, persona: str) -> None:
        if persona not in VALID_PERSONAS:
            raise InvalidPersonaError(
                f"Unknown persona '{persona}'. Valid personas: {VALID_PERSONAS}"
            )

    def generate(
        self, persona: str, api_key: str, *, base_url: str = "", model: str = "", max_retries: int = 3
    ) -> tuple[FullPayload, int]:
        """Call LLM to generate a FullPayload. Returns (payload, attempts_used)."""
        client = create_client(api_key, base_url)
        effective_model = model or GENERATION_MODEL
        last_error: str | None = None

        for attempt in range(1, max_retries + 1):
            if last_error and attempt > 1:
                messages = [
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Generate profile for: {persona}"},
                    {"role": "assistant", "content": "I will retry with a corrected response."},
                    {
                        "role": "user",
                        "content": (
                            f"Your previous output was invalid. Error: {last_error}\n"
                            "Please fix it and output valid JSON exactly matching the schema."
                        ),
                    },
                ]
            else:
                messages = [
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Generate profile for: {persona}"},
                ]

            logger.debug(f"PersonaGenerator attempt {attempt}/{max_retries} for '{persona}'")
            response = client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=GENERATION_TEMPERATURE,
                max_tokens=GENERATION_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content

            try:
                data = json.loads(raw)
                payload = FullPayload(**data)
                return payload, attempt
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                last_error = str(exc)
                logger.warning(f"Attempt {attempt} failed: {last_error}")

        raise GenerationError(
            f"Failed to generate valid payload for '{persona}' after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
