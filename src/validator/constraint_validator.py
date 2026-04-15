"""ConstraintValidator: runs LLM call #2 and diffs against LLM-generated softConstraints."""
from __future__ import annotations

import json

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import Discrepancy, SoftConstraints, ValidationReport
from src.config.llm_config import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_MODEL,
    EXTRACTION_TEMPERATURE,
    create_groq_client,
)
from src.generator.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT

_SC_FIELDS = [
    "consecutiveShiftLimits",
    "dailyTimeRestrictions",
    "recurringTimeOffPatterns",
    "crossDayDependencies",
    "weeklyFrequencyLimits",
    "conditionalRestrictions",
    "advanceNoticeRequired",
    "crewSizeRestrictions",
    "leadershipRestrictions",
    "jobTypeRestrictions",
    "vehicleRestrictions",
    "interpersonalConflicts",
]


def _is_empty(value) -> bool:
    """True if value is None, empty list, or a dict/model with all-None values."""
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        # model_dump() output: treat as empty only if all values are None
        return all(v is None for v in value.values())
    if hasattr(value, "model_dump"):
        return all(v is None for v in value.model_dump().values())
    return False


class ConstraintValidator:
    def validate(
        self,
        limitation_instructions: str,
        llm_soft_constraints: SoftConstraints,
        api_key: str,
    ) -> ValidationReport:
        """Run extraction on limitationInstructions, diff against llm_soft_constraints."""
        client = create_groq_client(api_key)
        try:
            response = client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": limitation_instructions},
                ],
                temperature=EXTRACTION_TEMPERATURE,
                max_tokens=EXTRACTION_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            extractor_sc = SoftConstraints(**data)
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning(f"ExtractionValidator failed: {exc} -- returning low-confidence report")
            return ValidationReport(
                passed=False,
                confidence="low",
                discrepancies=[
                    Discrepancy(field="*", type="extractor_only", note=f"Extractor call failed: {exc}")
                ],
            )

        discrepancies = self._diff(llm=llm_soft_constraints, extractor=extractor_sc)
        return self._build_report(discrepancies)

    def _diff(self, llm: SoftConstraints, extractor: SoftConstraints) -> list[Discrepancy]:
        """Field-level presence diff between LLM-generated and extracted softConstraints."""
        discrepancies: list[Discrepancy] = []
        llm_data = llm.model_dump()
        ext_data = extractor.model_dump()

        for field in _SC_FIELDS:
            llm_val = llm_data.get(field)
            ext_val = ext_data.get(field)
            llm_empty = _is_empty(llm_val)
            ext_empty = _is_empty(ext_val)

            if llm_empty and ext_empty:
                continue
            elif not llm_empty and ext_empty:
                discrepancies.append(
                    Discrepancy(
                        field=field,
                        type="generated_only",
                        note="LLM generated but extractor did not find",
                    )
                )
            elif llm_empty and not ext_empty:
                discrepancies.append(
                    Discrepancy(
                        field=field,
                        type="extractor_only",
                        note="Extractor found but LLM did not generate",
                    )
                )
            elif llm_val != ext_val:
                discrepancies.append(
                    Discrepancy(
                        field=field,
                        type="divergent",
                        note="Both present but values differ",
                    )
                )

        return discrepancies

    def _build_report(self, discrepancies: list[Discrepancy]) -> ValidationReport:
        extractor_only = [d for d in discrepancies if d.type == "extractor_only"]
        count = len(discrepancies)
        passed = len(extractor_only) == 0
        if count == 0:
            confidence = "high"
        elif count <= 2:
            confidence = "medium"
        else:
            confidence = "low"
        return ValidationReport(passed=passed, confidence=confidence, discrepancies=discrepancies)
