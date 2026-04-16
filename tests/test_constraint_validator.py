import json
from unittest.mock import MagicMock, patch

import pytest

from src.api.schemas.payload import SoftConstraints, DailyTimeRestrictions, ValidationReport
from src.validator.constraint_validator import QualityGate


QUALITY_PASS = {"passed": True, "confidence": "high", "issues": []}
QUALITY_FAIL = {
    "passed": False,
    "confidence": "low",
    "issues": ["crossDayDependencies present but no night shift in text"],
}


def _mock_client(response_dict: dict) -> MagicMock:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=json.dumps(response_dict)))
    ]
    return mock_client


def test_evaluate_returns_passed_report():
    qg = QualityGate()
    with patch("src.validator.constraint_validator.create_client", return_value=_mock_client(QUALITY_PASS)):
        report = qg.evaluate(
            limitation_instructions="Must not start before 14:00.",
            soft_constraints=SoftConstraints(
                dailyTimeRestrictions=DailyTimeRestrictions(startTimeAfter="14:00")
            ),
            api_key="fake",
        )
    assert report.passed is True
    assert report.confidence == "high"
    assert report.issues == []


def test_evaluate_returns_failed_report():
    qg = QualityGate()
    with patch("src.validator.constraint_validator.create_client", return_value=_mock_client(QUALITY_FAIL)):
        report = qg.evaluate(
            limitation_instructions="Must not start before 14:00.",
            soft_constraints=SoftConstraints(),
            api_key="fake",
        )
    assert report.passed is False
    assert report.confidence == "low"
    assert len(report.issues) == 1


def test_evaluate_falls_back_on_parse_failure():
    qg = QualityGate()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="not json"))
    ]
    with patch("src.validator.constraint_validator.create_client", return_value=mock_client):
        report = qg.evaluate(
            limitation_instructions="Must not start before 14:00.",
            soft_constraints=SoftConstraints(),
            api_key="fake",
        )
    assert report.passed is False
    assert report.confidence == "low"
    assert any("failed" in issue.lower() for issue in report.issues)


def test_evaluate_includes_both_inputs_in_user_message():
    qg = QualityGate()
    captured_messages = []

    def capture_call(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        mock = MagicMock()
        mock.choices = [MagicMock(message=MagicMock(content=json.dumps(QUALITY_PASS)))]
        return mock

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = capture_call

    with patch("src.validator.constraint_validator.create_client", return_value=mock_client):
        qg.evaluate(
            limitation_instructions="Must not start before 14:00.",
            soft_constraints=SoftConstraints(),
            api_key="fake",
        )

    user_msg = next(m["content"] for m in captured_messages if m["role"] == "user")
    assert "limitationInstructions" in user_msg
    assert "softConstraints" in user_msg
