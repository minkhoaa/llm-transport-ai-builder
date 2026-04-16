"""PersonaGenerator: validates persona name and drives the 3-call pipeline."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import FullPayload, LimitationProfile, PartialPayload, SoftConstraints
from src.config.llm_config import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_MODEL,
    EXTRACTION_TEMPERATURE,
    GENERATION_MAX_TOKENS,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    create_client,
)
from src.generator.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT
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


def _random_future_date() -> str:
    """Return a random future date between 1 week and 18 months from today."""
    today = date.today()
    days_ahead = random.randint(7, 548)
    return (today + timedelta(days=days_ahead)).isoformat()


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
        self,
        persona: str,
        api_key: str,
        *,
        base_url: str = "",
        model: str = "",
        max_retries: int = 3,
    ) -> tuple[FullPayload, SoftConstraints, int]:
        """Run 3-call pipeline. Returns (full_payload, soft_constraints, attempts_used)."""
        client = create_client(api_key, base_url)
        gen_model = model or GENERATION_MODEL
        ext_model = model or EXTRACTION_MODEL

        # --- Call 1: Profile generator ---
        last_error: str | None = None
        partial: PartialPayload | None = None

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

            logger.debug(f"Call 1 attempt {attempt}/{max_retries} for '{persona}'")
            response = client.chat.completions.create(
                model=gen_model,
                messages=messages,
                temperature=GENERATION_TEMPERATURE,
                max_tokens=GENERATION_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw1 = response.choices[0].message.content

            try:
                data1 = json.loads(raw1)
                data1.pop("_reasoning", None)  # strip CoT -- never exposed
                partial = PartialPayload(**data1)
                partial.employee.personalities = [persona]  # lock to selected persona
                break
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                last_error = str(exc)
                logger.warning(f"Call 1 attempt {attempt} failed: {last_error}")
        else:
            raise GenerationError(
                f"Call 1 failed for '{persona}' after {max_retries} attempts. "
                f"Last error: {last_error}"
            )

        attempts_used = attempt

        # --- Call 2: Constraint extractor ---
        soft: SoftConstraints = SoftConstraints()
        for ext_attempt in range(1, 3):  # up to 2 retries
            logger.debug(f"Call 2 attempt {ext_attempt}/2 for '{persona}'")
            try:
                response2 = client.chat.completions.create(
                    model=ext_model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": partial.limitation.limitationInstructions},
                    ],
                    temperature=EXTRACTION_TEMPERATURE,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                raw2 = response2.choices[0].message.content
                soft = SoftConstraints(**json.loads(raw2))
                break
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                logger.warning(f"Call 2 attempt {ext_attempt} failed: {exc}")
                if ext_attempt == 2:
                    logger.warning("Call 2 exhausted retries -- using empty SoftConstraints")

        # --- Assemble full payload ---
        payload = FullPayload(
            employee=partial.employee,
            limitation=LimitationProfile(
                effectiveDate=_random_future_date(),
                limitationInstructions=partial.limitation.limitationInstructions,
            ),
            skills=partial.skills,
            softConstraints=soft,
        )

        return payload, soft, attempts_used
