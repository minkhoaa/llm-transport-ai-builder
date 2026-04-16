"""Pydantic models for builder payload input and output."""
from __future__ import annotations

import random
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator, model_serializer

from src.config.clients import CLIENT_IDS, CLIENT_NAMES


def _random_id() -> int:
    return random.randint(100, 10_000)

# Hours of scheduling capacity represented by each AM or PM availability slot.
# Exposed as a constant so downstream tools (prompts, tests) can stay in sync.
HOURS_PER_SLOT: int = 5

JobType = Literal["MOV", "WH", "HHG"]

Rating = Literal[
    "1 - Poor",
    "2 - Needs Improvement",
    "3 - Standard",
    "4 - Above Average",
    "5 - Exceptional",
]


# --- Company reference ---

class CompanyRef(BaseModel):
    clientId: int
    clientName: str


# --- Employee ---

class EmployeeProfile(BaseModel):
    id: int = Field(default_factory=_random_id)

    @field_validator("id", mode="before")
    @classmethod
    def generate_id_if_none(cls, v: object) -> int:
        if v is None:
            return _random_id()
        return int(v)

    name: str
    priority: Literal["Regular", "Part-Time", "Extras"]
    rating: Rating
    prefHrs: int = Field(ge=0, le=168)
    mondayAm: bool
    mondayPm: bool
    tuesdayAm: bool
    tuesdayPm: bool
    wednesdayAm: bool
    wednesdayPm: bool
    thursdayAm: bool
    thursdayPm: bool
    fridayAm: bool
    fridayPm: bool
    saturdayAm: bool
    saturdayPm: bool
    sundayAm: bool
    sundayPm: bool
    personalities: List[str]
    additionalNotes: str
    preferredJobTypes: List[JobType] = Field(default_factory=list)
    avoidedJobTypes: List[JobType] = Field(default_factory=list)
    lovedByCompanies: List[CompanyRef]
    hatedByCompanies: List[CompanyRef]

    @model_validator(mode="after")
    def check_company_refs(self) -> "EmployeeProfile":
        """Every company in lovedByCompanies/hatedByCompanies must exist in the client registry."""
        for ref in self.lovedByCompanies + self.hatedByCompanies:
            if ref.clientId not in CLIENT_IDS:
                raise ValueError(
                    f"clientId {ref.clientId} not in client registry."
                )
            if ref.clientName not in CLIENT_NAMES:
                raise ValueError(
                    f"clientName '{ref.clientName}' not in client registry. "
                    f"Use the exact name from the Client Registry list."
                )
        return self

    @model_validator(mode="after")
    def check_no_overlap(self) -> "EmployeeProfile":
        overlap = set(self.preferredJobTypes) & set(self.avoidedJobTypes)
        if overlap:
            raise ValueError(
                f"Job types cannot appear in both preferredJobTypes and avoidedJobTypes: {overlap}"
            )
        return self

    @model_validator(mode="after")
    def check_prefhrs_vs_availability(self) -> "EmployeeProfile":
        """prefHrs must not exceed what the available AM/PM slots can physically support.

        Each AM or PM slot represents ~5 hours of scheduling capacity.
        A worker with 2 slots cannot prefer 40 hours per week.
        """
        slots = sum([
            self.mondayAm, self.mondayPm,
            self.tuesdayAm, self.tuesdayPm,
            self.wednesdayAm, self.wednesdayPm,
            self.thursdayAm, self.thursdayPm,
            self.fridayAm, self.fridayPm,
            self.saturdayAm, self.saturdayPm,
            self.sundayAm, self.sundayPm,
        ])
        max_hrs = slots * HOURS_PER_SLOT
        if self.prefHrs > max_hrs:
            raise ValueError(
                f"prefHrs ({self.prefHrs}) exceeds weekly availability: "
                f"{slots} slot(s) × {HOURS_PER_SLOT}h = {max_hrs}h max. "
                f"Lower prefHrs or enable more AM/PM slots."
            )
        return self


# --- Limitation ---

class LimitationProfile(BaseModel):
    effectiveDate: str
    limitationInstructions: str


# --- Intermediate schema (Call 1 output — no softConstraints, no effectiveDate) ---

class PartialLimitation(BaseModel):
    """Call 1 output: only the text, no effectiveDate."""
    limitationInstructions: str


class PartialPayload(BaseModel):
    """Output of Call 1 — no softConstraints."""
    employee: EmployeeProfile
    limitation: PartialLimitation
    skills: List[str]


# --- softConstraints sub-models ---

class ConsecutiveShiftLimit(BaseModel):
    shiftType: Literal["evening", "morning", "night", "day", "any"]
    maxConsecutive: int
    timeUnit: Literal["shifts", "days"]


class DailyTimeRestrictions(BaseModel):
    startTimeAfter: Optional[str] = None
    endTimeBefore: Optional[str] = None
    maxDailyHours: Optional[float] = None
    appliesToDays: Optional[List[str]] = None


class RecurringTimeOffPattern(BaseModel):
    pattern: str
    timeUnit: str
    appliesToDays: List[str]
    startWeekUnknown: bool


class CrossDayDependency(BaseModel):
    ifShift: str
    thenCannotWork: str
    nextDayOffset: int


class WeeklyFrequencyLimit(BaseModel):
    shiftType: str
    maxPerWeek: int


class ConditionalTrigger(BaseModel):
    type: Literal["job_assignment", "shift_scheduled", "day_of_week"]
    clientName: Optional[str] = None
    shiftType: str
    dayOffset: int


class ConditionalConsequence(BaseModel):
    action: Literal["cannot_assign", "requires_notice", "avoid_if_possible"]
    toShiftType: str
    onDayOffset: int


class ConditionalRestriction(BaseModel):
    trigger: ConditionalTrigger
    consequence: ConditionalConsequence
    originalPhrase: Optional[str] = None


class AdvanceNoticeRequired(BaseModel):
    shiftType: str
    daysRequired: int
    ambiguous: bool


class CrewSizeRestrictions(BaseModel):
    minCrewSize: Optional[int] = None
    maxCrewSize: Optional[int] = None
    allowedSizes: Optional[List[int]] = None
    appliesToLeadershipOnly: bool = False


class LeadershipRestriction(BaseModel):
    maxCrewSize: Optional[int] = None
    allowedJobTypes: Optional[List[str]] = None
    entityResolutionRequired: bool = False


class JobTypeRestrictions(BaseModel):
    whitelist: Optional[List[str]] = None
    blacklist: Optional[List[str]] = None
    whitelistClients: Optional[List[str]] = None
    blacklistClients: Optional[List[str]] = None
    entityResolutionRequired: bool = False


class VehicleRestriction(BaseModel):
    vehicleType: Literal["truck", "van", "any"]
    restrictionType: Literal["no_day_and_night", "no_double", "cannot_drive"]


class InterpersonalConflict(BaseModel):
    conflictEmployeeName: str
    conflictType: Literal["cannot_work_together", "avoid_if_possible"]
    softConstraint: bool


class PhysicalRestrictions(BaseModel):
    """Medical/physical constraints not expressible via scheduling categories."""
    maxLiftKg: Optional[int] = None

    @field_validator("maxLiftKg", mode="before")
    @classmethod
    def coerce_float_to_int(cls, v: object) -> object:
        if isinstance(v, float):
            return round(v)
        return v
    # suggested values: "stair_carry", "heavy_carry", "overhead_work",
    #                   "heavy_equipment_operation", "repetitive_lifting"
    bannedTasks: Optional[List[str]] = None
    # suggested values: "dusty", "chemical", "outdoor", "cold_storage"
    restrictedEnvironments: Optional[List[str]] = None
    # Only set when explicitly stated in the text
    dutyLevel: Optional[Literal["light", "medium", "full"]] = None
    noteSummary: Optional[str] = None


# --- SoftConstraints aggregate ---

class SoftConstraints(BaseModel):
    consecutiveShiftLimits: List[ConsecutiveShiftLimit] = []
    dailyTimeRestrictions: Optional[DailyTimeRestrictions] = None
    recurringTimeOffPatterns: List[RecurringTimeOffPattern] = []
    crossDayDependencies: List[CrossDayDependency] = []
    weeklyFrequencyLimits: List[WeeklyFrequencyLimit] = []
    conditionalRestrictions: List[ConditionalRestriction] = []
    advanceNoticeRequired: List[AdvanceNoticeRequired] = []
    crewSizeRestrictions: Optional[CrewSizeRestrictions] = None
    leadershipRestrictions: List[LeadershipRestriction] = []
    jobTypeRestrictions: Optional[JobTypeRestrictions] = None
    vehicleRestrictions: List[VehicleRestriction] = []
    interpersonalConflicts: List[InterpersonalConflict] = []
    physicalRestrictions: Optional[PhysicalRestrictions] = None

    @model_serializer(mode="wrap")
    def exclude_empty(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        return {k: v for k, v in data.items() if v is not None and v != []}


# --- Full payload ---

class FullPayload(BaseModel):
    employee: EmployeeProfile
    limitation: LimitationProfile
    skills: List[str]
    softConstraints: SoftConstraints


# --- Validation report ---

class ValidationReport(BaseModel):
    passed: bool
    confidence: Literal["high", "medium", "low"]
    issues: List[str]  # natural language descriptions from Call 3


# --- API request / response ---

class GenerateRequest(BaseModel):
    persona: str
    api_key: str
    provider: str = "groq"          # known key from PROVIDER_URLS, or "custom"
    base_url: Optional[str] = None  # only used when provider="custom"
    model: Optional[str] = None     # overrides GENERATION_MODEL env var when set
    excluded_names: List[str] = Field(default_factory=list)  # names already in DB


class BatchGenerateRequest(BaseModel):
    personas: Optional[List[str]] = None
    persona: Optional[str] = None
    count: int = Field(default=1, ge=1, le=20)
    api_key: str
    provider: str = "groq"
    base_url: Optional[str] = None
    model: Optional[str] = None
    excluded_names: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_persona_source(self) -> "BatchGenerateRequest":
        if not self.personas and not self.persona:
            raise ValueError("Provide either 'personas' list or 'persona' + 'count'")
        return self


class GenerateResponse(BaseModel):
    persona: str
    attempts: int
    model: str
    payload: FullPayload
    validation: ValidationReport


class BatchGenerateResponse(BaseModel):
    total: int
    failed: int
    profiles: List[GenerateResponse]
