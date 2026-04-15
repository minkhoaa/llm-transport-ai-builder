import pytest
from unittest.mock import MagicMock

from src.api.schemas.payload import (
    BatchGenerateRequest, FullPayload, GenerateResponse, SoftConstraints,
    ValidationReport, EmployeeProfile, LimitationProfile,
)
from src.services.builder_service import BuilderService
from src.generator.persona_generator import InvalidPersonaError, GenerationError


def _make_payload():
    return FullPayload(
        employee=EmployeeProfile(
            name="Test User", priority="Regular", rating=3, prefHrs=40,
            mondayAm=True, mondayPm=True, tuesdayAm=True, tuesdayPm=True,
            wednesdayAm=True, wednesdayPm=True, thursdayAm=True, thursdayPm=True,
            fridayAm=True, fridayPm=True, saturdayAm=False, saturdayPm=False,
            sundayAm=False, sundayPm=False,
            personalities=["Test"], additionalNotes="",
            preferredJobTypes=[], avoidedJobTypes=[],
            lovedByCompanies=[], hatedByCompanies=[],
        ),
        limitation=LimitationProfile(effectiveDate="2026-05-01", limitationInstructions="Must not work nights."),
        skills=[],
        softConstraints=SoftConstraints(),
    )


def _make_report(passed=True):
    return ValidationReport(passed=passed, confidence="high", discrepancies=[])


def test_generate_single_returns_response():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.return_value = (_make_payload(), 1)
    val = MagicMock()
    val.validate.return_value = _make_report()

    service = BuilderService(generator=gen, validator=val)
    response = service.generate_single("Night Owl", "fake_key")

    assert isinstance(response, GenerateResponse)
    assert response.persona == "Night Owl"
    assert response.attempts == 1


def test_generate_single_raises_on_invalid_persona():
    gen = MagicMock()
    gen.validate_persona.side_effect = InvalidPersonaError("Unknown")
    service = BuilderService(generator=gen, validator=MagicMock())

    with pytest.raises(InvalidPersonaError):
        service.generate_single("Pirate", "fake_key")


def test_generate_batch_with_persona_and_count():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.return_value = (_make_payload(), 1)
    val = MagicMock()
    val.validate.return_value = _make_report()

    service = BuilderService(generator=gen, validator=val)
    request = BatchGenerateRequest(persona="Night Owl", count=3, api_key="fake")
    response = service.generate_batch(request)

    assert response.total == 3
    assert response.failed == 0
    assert len(response.profiles) == 3


def test_generate_batch_with_explicit_personas():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.return_value = (_make_payload(), 1)
    val = MagicMock()
    val.validate.return_value = _make_report()

    service = BuilderService(generator=gen, validator=val)
    request = BatchGenerateRequest(personas=["Night Owl", "Early Bird"], api_key="fake")
    response = service.generate_batch(request)

    assert response.total == 2
    assert len(response.profiles) == 2


def test_generate_batch_partial_failure():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.side_effect = [(_make_payload(), 1), GenerationError("failed")]
    val = MagicMock()
    val.validate.return_value = _make_report()

    service = BuilderService(generator=gen, validator=val)
    request = BatchGenerateRequest(personas=["Night Owl", "Early Bird"], api_key="fake")
    response = service.generate_batch(request)

    assert response.total == 2
    assert response.failed == 1
    assert len(response.profiles) == 1
