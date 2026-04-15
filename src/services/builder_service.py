"""BuilderService: orchestrates single and batch profile generation."""
from __future__ import annotations

from loguru import logger

from src.api.schemas.payload import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    GenerateResponse,
)
from src.config.llm_config import GENERATION_MODEL, resolve_base_url
from src.generator.persona_generator import GenerationError, PersonaGenerator
from src.validator.constraint_validator import ConstraintValidator


class BuilderService:
    def __init__(self, generator: PersonaGenerator, validator: ConstraintValidator):
        self._generator = generator
        self._validator = validator

    def generate_single(self, persona: str, api_key: str, base_url: str = "") -> GenerateResponse:
        self._generator.validate_persona(persona)
        payload, attempts = self._generator.generate(persona, api_key, base_url=base_url)
        validation = self._validator.validate(
            limitation_instructions=payload.limitation.limitationInstructions,
            llm_soft_constraints=payload.softConstraints,
            api_key=api_key,
            base_url=base_url,
        )
        return GenerateResponse(
            persona=persona,
            attempts=attempts,
            model=GENERATION_MODEL,
            payload=payload,
            validation=validation,
        )

    def generate_batch(self, request: BatchGenerateRequest) -> BatchGenerateResponse:
        base_url = resolve_base_url(request.provider, request.base_url or "")
        personas = request.personas if request.personas else [request.persona] * request.count
        profiles: list[GenerateResponse] = []
        failed = 0

        for persona in personas:
            try:
                response = self.generate_single(persona, request.api_key, base_url)
                profiles.append(response)
            except Exception as exc:
                logger.warning(f"Batch generation failed for '{persona}': {exc}")
                failed += 1

        return BatchGenerateResponse(total=len(personas), failed=failed, profiles=profiles)
