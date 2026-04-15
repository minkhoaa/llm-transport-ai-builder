import json
from unittest.mock import MagicMock, patch

import pytest

from src.api.schemas.payload import (
    SoftConstraints,
    ConsecutiveShiftLimit,
    DailyTimeRestrictions,
    Discrepancy,
)
from src.validator.constraint_validator import ConstraintValidator


def make_sc(**kwargs) -> SoftConstraints:
    return SoftConstraints(**kwargs)


def test_diff_no_discrepancies_when_identical():
    v = ConstraintValidator()
    sc = make_sc(consecutiveShiftLimits=[ConsecutiveShiftLimit(shiftType="evening", maxConsecutive=2, timeUnit="shifts")])
    discrepancies = v._diff(llm=sc, extractor=sc)
    assert discrepancies == []


def test_diff_generated_only_when_extractor_empty():
    v = ConstraintValidator()
    llm = make_sc(dailyTimeRestrictions=DailyTimeRestrictions(startTimeAfter="09:00"))
    extractor = make_sc()
    discrepancies = v._diff(llm=llm, extractor=extractor)
    assert any(d.type == "generated_only" for d in discrepancies)


def test_diff_extractor_only_when_llm_empty():
    v = ConstraintValidator()
    extractor = make_sc(dailyTimeRestrictions=DailyTimeRestrictions(startTimeAfter="09:00"))
    llm = make_sc()
    discrepancies = v._diff(llm=llm, extractor=extractor)
    assert any(d.type == "extractor_only" for d in discrepancies)


def test_confidence_high_on_zero_discrepancies():
    v = ConstraintValidator()
    report = v._build_report([])
    assert report.confidence == "high"
    assert report.passed is True


def test_confidence_low_on_three_or_more():
    v = ConstraintValidator()
    discrepancies = [
        Discrepancy(field="f1", type="extractor_only", note=""),
        Discrepancy(field="f2", type="extractor_only", note=""),
        Discrepancy(field="f3", type="extractor_only", note=""),
    ]
    report = v._build_report(discrepancies)
    assert report.confidence == "low"
    assert report.passed is False


def test_validate_calls_groq_and_returns_report():
    v = ConstraintValidator()
    extractor_output = {"dailyTimeRestrictions": {"startTimeAfter": "14:00"}}
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=json.dumps(extractor_output)))
    ]
    llm_sc = SoftConstraints()  # empty — extractor finds constraint LLM missed
    with patch("src.validator.constraint_validator.create_groq_client", return_value=mock_client):
        report = v.validate(
            limitation_instructions="Must not start before 2pm.",
            llm_soft_constraints=llm_sc,
            api_key="fake",
        )
    assert report.confidence in ("high", "medium", "low")
    # extractor found a constraint the LLM missed — should be extractor_only
    assert report.passed is False
    assert any(d.type == "extractor_only" for d in report.discrepancies)
