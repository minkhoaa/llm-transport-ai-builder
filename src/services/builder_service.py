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
from src.validator.constraint_validator import QualityGate


class BuilderService:
    def __init__(self, generator: PersonaGenerator, quality_gate: QualityGate):
        self._generator = generator
        self._quality_gate = quality_gate

    def generate_single(
        self, persona: str, api_key: str, base_url: str = "", model: str = "",
        excluded_names: list[str] | None = None,
    ) -> GenerateResponse:
        self._generator.validate_persona(persona)
        payload, soft, attempts = self._generator.generate(
            persona, api_key, base_url=base_url, model=model, excluded_names=excluded_names
        )
        validation = self._quality_gate.evaluate(
            limitation_instructions=payload.limitation.limitationInstructions,
            soft_constraints=soft,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        effective_model = model or GENERATION_MODEL
        return GenerateResponse(
            persona=persona,
            attempts=attempts,
            model=effective_model,
            payload=payload,
            validation=validation,
        )

    def generate_batch(self, request: BatchGenerateRequest) -> BatchGenerateResponse:
        base_url = resolve_base_url(request.provider, request.base_url or "")
        model = request.model or ""
        personas = request.personas if request.personas else [request.persona] * request.count
        profiles: list[GenerateResponse] = []
        failed = 0

        excluded = list(request.excluded_names)
        for persona in personas:
            try:
                response = self.generate_single(persona, request.api_key, base_url, model, excluded)
                excluded.append(response.payload.employee.name)  # grow list within batch
                profiles.append(response)
            except Exception as exc:
                logger.warning(f"Batch generation failed for '{persona}': {exc}")
                failed += 1

        return BatchGenerateResponse(total=len(personas), failed=failed, profiles=profiles)
