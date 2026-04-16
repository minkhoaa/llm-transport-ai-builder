import json
from unittest.mock import MagicMock, patch

import pytest

from src.generator.persona_generator import (
    GenerationError,
    InvalidPersonaError,
    PersonaGenerator,
    VALID_PERSONAS,
)

# Call 1 output: PartialPayload-compatible (with _reasoning, no softConstraints, no effectiveDate)
VALID_CALL1 = {
    "_reasoning": {
        "schedule": "Night Owl avoids mornings",
        "skills": "Heavy Carry suits this persona",
        "priority": "Regular",
        "limitation_plan": "dailyTimeRestrictions",
    },
    "employee": {
        "id": None, "name": "Tom Nguyen", "priority": "Regular",
        "rating": "3 - Standard", "prefHrs": 40,
        "mondayAm": False, "mondayPm": True,
        "tuesdayAm": False, "tuesdayPm": True,
        "wednesdayAm": False, "wednesdayPm": True,
        "thursdayAm": False, "thursdayPm": True,
        "fridayAm": False, "fridayPm": True,
        "saturdayAm": False, "saturdayPm": False,
        "sundayAm": False, "sundayPm": False,
        "personalities": ["Night Owl"],
        "additionalNotes": "Prefers late evenings.",
        "preferredJobTypes": ["WH"], "avoidedJobTypes": [],
        "lovedByCompanies": [], "hatedByCompanies": [],
    },
    "skills": ["Heavy Carry"],
    "limitation": {
        "limitationInstructions": "Must not start before 2pm.",
    },
}

# Call 2 output: SoftConstraints-compatible
VALID_CALL2 = {
    "dailyTimeRestrictions": {"startTimeAfter": "14:00"},
}


def _make_response(content: str) -> MagicMock:
    return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])


def test_invalid_persona_raises():
    gen = PersonaGenerator()
    with pytest.raises(InvalidPersonaError):
        gen.validate_persona("Pirate")


def test_valid_persona_does_not_raise():
    gen = PersonaGenerator()
    gen.validate_persona("Night Owl")


def test_all_27_personas_valid():
    gen = PersonaGenerator()
    for p in VALID_PERSONAS:
        gen.validate_persona(p)


def test_generate_returns_payload_on_valid_response():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_response(json.dumps(VALID_CALL1)),  # Call 1
        _make_response(json.dumps(VALID_CALL2)),  # Call 2
    ]
    with patch("src.generator.persona_generator.create_client", return_value=mock_client):
        payload, soft, attempts = gen.generate("Night Owl", "fake_key")
    assert payload.employee.name == "Tom Nguyen"
    assert payload.employee.personalities == ["Night Owl"]
    assert soft.dailyTimeRestrictions.startTimeAfter == "14:00"
    assert attempts == 1


def test_generate_strips_reasoning_field():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_response(json.dumps(VALID_CALL1)),
        _make_response(json.dumps(VALID_CALL2)),
    ]
    with patch("src.generator.persona_generator.create_client", return_value=mock_client):
        payload, soft, attempts = gen.generate("Night Owl", "fake_key")
    payload_dict = payload.model_dump()
    assert "_reasoning" not in payload_dict
    assert "_reasoning" not in payload_dict.get("employee", {})


def test_generate_retries_call1_on_invalid_json():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_response("not json"),               # Call 1 attempt 1 -- fail
        _make_response(json.dumps(VALID_CALL1)),  # Call 1 attempt 2 -- success
        _make_response(json.dumps(VALID_CALL2)),  # Call 2
    ]
    with patch("src.generator.persona_generator.create_client", return_value=mock_client):
        payload, soft, attempts = gen.generate("Night Owl", "fake_key")
    assert attempts == 2


def test_generate_raises_after_call1_max_retries():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_response("bad json")
    with patch("src.generator.persona_generator.create_client", return_value=mock_client):
        with pytest.raises(GenerationError):
            gen.generate("Night Owl", "fake_key", max_retries=3)


def test_generate_falls_back_to_empty_soft_on_call2_failure():
    from src.api.schemas.payload import SoftConstraints
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_response(json.dumps(VALID_CALL1)),  # Call 1 -- success
        _make_response("bad json"),               # Call 2 attempt 1 -- fail
        _make_response("bad json"),               # Call 2 attempt 2 -- fail
    ]
    with patch("src.generator.persona_generator.create_client", return_value=mock_client):
        payload, soft, attempts = gen.generate("Night Owl", "fake_key")
    assert isinstance(soft, SoftConstraints)
    assert soft.dailyTimeRestrictions is None
