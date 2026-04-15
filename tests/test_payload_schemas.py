import pytest
from pydantic import ValidationError

from src.api.schemas.payload import (
    EmployeeProfile,
    FullPayload,
    LimitationProfile,
    SoftConstraints,
    GenerateRequest,
    BatchGenerateRequest,
)


def make_employee(**overrides):
    base = {
        "name": "Jane Doe", "priority": "Regular", "rating": "3 - Standard", "prefHrs": 40,
        "mondayAm": True, "mondayPm": True, "tuesdayAm": True, "tuesdayPm": True,
        "wednesdayAm": True, "wednesdayPm": True, "thursdayAm": True, "thursdayPm": True,
        "fridayAm": True, "fridayPm": True, "saturdayAm": False, "saturdayPm": False,
        "sundayAm": False, "sundayPm": False,
        "personalities": ["Regular worker"],
        "additionalNotes": "None",
        "preferredJobTypes": ["HHG"], "avoidedJobTypes": [],
        "lovedByCompanies": [], "hatedByCompanies": [],
    }
    return {**base, **overrides}


def test_employee_priority_valid():
    e = EmployeeProfile(**make_employee(priority="Part-Time"))
    assert e.priority == "Part-Time"


def test_employee_priority_invalid():
    with pytest.raises(ValidationError):
        EmployeeProfile(**make_employee(priority="Full-Time"))


def test_employee_rating_valid_labels():
    from src.api.schemas.payload import Rating
    for label in ("1 - Poor", "2 - Needs Improvement", "3 - Standard", "4 - Above Average", "5 - Exceptional"):
        e = EmployeeProfile(**make_employee(rating=label))
        assert e.rating == label


def test_employee_rating_invalid_label():
    with pytest.raises(ValidationError):
        EmployeeProfile(**make_employee(rating="3"))  # bare integer string
    with pytest.raises(ValidationError):
        EmployeeProfile(**make_employee(rating=3))    # raw int


def test_employee_personalities_is_list():
    e = EmployeeProfile(**make_employee(personalities=["Night Owl"]))
    assert isinstance(e.personalities, list)


def test_employee_id_auto_generated():
    e = EmployeeProfile(**make_employee())
    assert isinstance(e.id, int) and e.id >= 1


def test_employee_id_unique_per_instance():
    e1 = EmployeeProfile(**make_employee())
    e2 = EmployeeProfile(**make_employee())
    assert e1.id != e2.id


def test_employee_id_null_becomes_int():
    e = EmployeeProfile(**make_employee(id=None))
    assert isinstance(e.id, int) and e.id >= 1


def test_job_type_invalid_value():
    with pytest.raises(ValidationError):
        EmployeeProfile(**make_employee(preferredJobTypes=["INVALID"]))


def test_job_type_overlap_rejected():
    with pytest.raises(ValidationError):
        EmployeeProfile(**make_employee(preferredJobTypes=["HHG"], avoidedJobTypes=["HHG"]))


def test_job_type_no_overlap_passes():
    e = EmployeeProfile(**make_employee(preferredJobTypes=["HHG", "WH"], avoidedJobTypes=["MOV"]))
    assert set(e.preferredJobTypes) & set(e.avoidedJobTypes) == set()


def test_batch_request_count_bounds():
    with pytest.raises(ValidationError):
        BatchGenerateRequest(persona="Night Owl", count=21, api_key="k")
    with pytest.raises(ValidationError):
        BatchGenerateRequest(persona="Night Owl", count=0, api_key="k")


def test_batch_request_needs_persona_or_personas():
    with pytest.raises(ValidationError):
        BatchGenerateRequest(api_key="k")  # neither personas nor persona provided
