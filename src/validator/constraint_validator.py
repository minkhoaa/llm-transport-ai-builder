"""QualityGate: LLM call #3 -- natural language evaluation of extracted constraints."""
from __future__ import annotations

import json

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import SoftConstraints, ValidationReport
from src.config.llm_config import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_MODEL,
    EXTRACTION_TEMPERATURE,
    create_client,
)
from src.generator.prompts.quality_prompt import QUALITY_SYSTEM_PROMPT


class QualityGate:
    def evaluate(
        self,
        limitation_instructions: str,
        soft_constraints: SoftConstraints,
        api_key: str,
        base_url: str = "",
        model: str = "",
    ) -> ValidationReport:
        """Call LLM to evaluate alignment between limitation text and extracted constraints."""
        client = create_client(api_key, base_url)
        effective_model = model or EXTRACTION_MODEL

        user_message = json.dumps(
            {
                "limitationInstructions": limitation_instructions,
                "softConstraints": soft_constraints.model_dump(exclude_none=True),
            },
            indent=2,
        )

        # Retry once on parse failure
        for attempt in range(1, 3):
            try:
                response = client.chat.completions.create(
                    model=effective_model,
                    messages=[
                        {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=EXTRACTION_TEMPERATURE,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                data = json.loads(raw)
                return ValidationReport(**data)
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                logger.warning(f"QualityGate attempt {attempt} failed: {exc}")

        return ValidationReport(
            passed=False,
            confidence="low",
            issues=["Quality gate call failed after 2 attempts"],
        )
