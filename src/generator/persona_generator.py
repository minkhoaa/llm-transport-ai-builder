"""PersonaGenerator: validates persona name and drives the 3-call pipeline."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import (
    AdvanceNoticeRequired,
    ConsecutiveShiftLimit,
    ConditionalRestriction,
    CrewSizeRestrictions,
    CrossDayDependency,
    DailyTimeRestrictions,
    FullPayload,
    InterpersonalConflict,
    JobTypeRestrictions,
    LeadershipRestriction,
    LimitationProfile,
    PartialPayload,
    PhysicalRestrictions,
    RecurringTimeOffPattern,
    SoftConstraints,
    VehicleRestriction,
    WeeklyFrequencyLimit,
)
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


_ARRAY_MODELS: list[tuple[str, type]] = [
    ("consecutiveShiftLimits", ConsecutiveShiftLimit),
    ("recurringTimeOffPatterns", RecurringTimeOffPattern),
    ("crossDayDependencies", CrossDayDependency),
    ("weeklyFrequencyLimits", WeeklyFrequencyLimit),
    ("conditionalRestrictions", ConditionalRestriction),
    ("advanceNoticeRequired", AdvanceNoticeRequired),
    ("leadershipRestrictions", LeadershipRestriction),
    ("vehicleRestrictions", VehicleRestriction),
    ("interpersonalConflicts", InterpersonalConflict),
]

_OBJECT_MODELS: list[tuple[str, type]] = [
    ("dailyTimeRestrictions", DailyTimeRestrictions),
    ("crewSizeRestrictions", CrewSizeRestrictions),
    ("jobTypeRestrictions", JobTypeRestrictions),
    ("physicalRestrictions", PhysicalRestrictions),
]


def _parse_soft_constraints_lenient(data: dict) -> SoftConstraints:
    """Parse SoftConstraints, dropping individual invalid items instead of failing entirely."""
    cleaned: dict = {}

    for field, model_cls in _ARRAY_MODELS:
        raw_items = data.get(field)
        if not isinstance(raw_items, list) or not raw_items:
            continue
        valid_items = []
        for item in raw_items:
            try:
                model_cls.model_validate(item)
                valid_items.append(item)
            except (ValidationError, Exception) as exc:
                logger.warning(f"Call 2: dropping invalid {field} item — {exc}")
        if valid_items:
            cleaned[field] = valid_items

    for field, model_cls in _OBJECT_MODELS:
        raw_obj = data.get(field)
        if raw_obj is None:
            continue
        try:
            model_cls.model_validate(raw_obj)
            cleaned[field] = raw_obj
        except (ValidationError, Exception) as exc:
            logger.warning(f"Call 2: dropping invalid {field} — {exc}")

    return SoftConstraints(**cleaned)


_EFFECTIVE_DATE_MIN_DAYS: int = 7    # earliest effective date: 1 week from today
_EFFECTIVE_DATE_MAX_DAYS: int = 548  # latest effective date: ~18 months from today
_CALL2_MAX_RETRIES: int = 2          # extraction call retry budget


def _random_future_date() -> str:
    """Return a random future date between _EFFECTIVE_DATE_MIN_DAYS and _EFFECTIVE_DATE_MAX_DAYS."""
    today = date.today()
    days_ahead = random.randint(_EFFECTIVE_DATE_MIN_DAYS, _EFFECTIVE_DATE_MAX_DAYS)
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
        excluded_names: list[str] | None = None,
    ) -> tuple[FullPayload, SoftConstraints, int]:
        """Run 3-call pipeline. Returns (full_payload, soft_constraints, attempts_used)."""
        client = create_client(api_key, base_url)
        gen_model = model or GENERATION_MODEL
        ext_model = model or EXTRACTION_MODEL

        user_prompt = f"Generate profile for: {persona}"
        if excluded_names:
            names_list = ", ".join(f'"{n}"' for n in excluded_names)
            user_prompt += f"\n\nDo NOT use any of these already-taken names: {names_list}. Choose a completely different name."

        # --- Call 1: Profile generator ---
        last_error: str | None = None
        partial: PartialPayload | None = None

        for attempt in range(1, max_retries + 1):
            if last_error and attempt > 1:
                messages = [
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
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
                    {"role": "user", "content": user_prompt},
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
                # Enforce name uniqueness at code level (LLM may ignore the prompt instruction)
                if excluded_names:
                    norm = lambda s: s.strip().lower()
                    if norm(partial.employee.name) in {norm(n) for n in excluded_names}:
                        raise ValueError(f"Name '{partial.employee.name}' is already taken — retrying")
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
        last_ext_error: str | None = None
        last_raw2: str = ""
        for ext_attempt in range(1, _CALL2_MAX_RETRIES + 1):
            logger.debug(f"Call 2 attempt {ext_attempt}/2 for '{persona}'")
            if last_ext_error:
                ext_messages = [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": partial.limitation.limitationInstructions},
                    {"role": "assistant", "content": last_raw2},
                    {
                        "role": "user",
                        "content": (
                            f"Your output had validation errors: {last_ext_error}\n"
                            "Fix the invalid values — check the STRICT ENUM VALUES section — "
                            "and output corrected JSON."
                        ),
                    },
                ]
            else:
                ext_messages = [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": partial.limitation.limitationInstructions},
                ]
            try:
                response2 = client.chat.completions.create(
                    model=ext_model,
                    messages=ext_messages,
                    temperature=EXTRACTION_TEMPERATURE,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                last_raw2 = response2.choices[0].message.content
                data2 = json.loads(last_raw2)
                soft = _parse_soft_constraints_lenient(data2)
                break
            except (json.JSONDecodeError, Exception) as exc:
                last_ext_error = str(exc)
                logger.warning(f"Call 2 attempt {ext_attempt} failed: {exc}")
                if ext_attempt == _CALL2_MAX_RETRIES:
                    logger.warning("Call 2 exhausted retries — using empty SoftConstraints")

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
