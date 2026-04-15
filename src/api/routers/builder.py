"""Builder API router: /builder/generate and /builder/generate/batch."""
from fastapi import APIRouter, HTTPException
from loguru import logger

from src.api.schemas.payload import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    GenerateRequest,
    GenerateResponse,
)
from src.config.llm_config import resolve_base_url
from src.generator.persona_generator import InvalidPersonaError, PersonaGenerator
from src.services.builder_service import BuilderService
from src.validator.constraint_validator import ConstraintValidator

router = APIRouter(prefix="/builder", tags=["builder"])

_generator = PersonaGenerator()
_validator = ConstraintValidator()
_service = BuilderService(generator=_generator, validator=_validator)


@router.post("/generate", response_model=GenerateResponse)
def generate_profile(request: GenerateRequest):
    base_url = resolve_base_url(request.provider, request.base_url or "")
    try:
        return _service.generate_single(request.persona, request.api_key, base_url)
    except InvalidPersonaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Generation failed: {exc}")
        raise HTTPException(status_code=422, detail={"status": "generation_failed", "reason": str(exc)})


@router.post("/generate/batch", response_model=BatchGenerateResponse)
def generate_batch(request: BatchGenerateRequest):
    return _service.generate_batch(request)
