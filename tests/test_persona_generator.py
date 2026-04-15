import json
from unittest.mock import MagicMock, patch

import pytest

from src.generator.persona_generator import PersonaGenerator, InvalidPersonaError, GenerationError, VALID_PERSONAS


VALID_PAYLOAD = {
    "employee": {
        "id": None, "name": "Tom Nguyen", "priority": "Regular", "rating": "3 - Standard", "prefHrs": 40,
        "mondayAm": False, "mondayPm": True, "tuesdayAm": False, "tuesdayPm": True,
        "wednesdayAm": False, "wednesdayPm": True, "thursdayAm": False, "thursdayPm": True,
        "fridayAm": False, "fridayPm": True, "saturdayAm": False, "saturdayPm": False,
        "sundayAm": False, "sundayPm": False,
        "personalities": ["Night Owl"],
        "additionalNotes": "Prefers late evenings.",
        "preferredJobTypes": ["WH"], "avoidedJobTypes": [],
        "lovedByCompanies": [], "hatedByCompanies": [],
    },
    "limitation": {"effectiveDate": "2026-05-01", "limitationInstructions": "Must not start before 2pm."},
    "skills": ["Heavy Carry"],
    "softConstraints": {
        "dailyTimeRestrictions": {"startTimeAfter": "14:00"},
    },
}


def _mock_groq_response(payload_dict: dict):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload_dict)
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    return mock_client


def test_invalid_persona_raises():
    gen = PersonaGenerator()
    with pytest.raises(InvalidPersonaError):
        gen.validate_persona("Pirate")


def test_valid_persona_does_not_raise():
    gen = PersonaGenerator()
    gen.validate_persona("Night Owl")  # should not raise


def test_all_27_personas_valid():
    gen = PersonaGenerator()
    for p in VALID_PERSONAS:
        gen.validate_persona(p)  # none should raise


def test_generate_returns_payload_on_valid_response():
    gen = PersonaGenerator()
    mock_client = _mock_groq_response(VALID_PAYLOAD)
    with patch("src.generator.persona_generator.create_groq_client", return_value=mock_client):
        payload, attempts = gen.generate("Night Owl", "fake_key")
    assert payload.employee.name == "Tom Nguyen"
    assert attempts == 1


def test_generate_retries_on_invalid_json():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="not json"))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(VALID_PAYLOAD)))]),
    ]
    with patch("src.generator.persona_generator.create_groq_client", return_value=mock_client):
        payload, attempts = gen.generate("Night Owl", "fake_key")
    assert attempts == 2


def test_generate_raises_after_max_retries():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="bad json"))
    ]
    with patch("src.generator.persona_generator.create_groq_client", return_value=mock_client):
        with pytest.raises(GenerationError):
            gen.generate("Night Owl", "fake_key", max_retries=3)
