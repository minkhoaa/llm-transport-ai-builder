"""Pydantic models for builder payload input and output."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# --- Company reference ---

class CompanyRef(BaseModel):
    clientId: int
    clientName: str


# --- Employee ---

class EmployeeProfile(BaseModel):
    id: None = None
    name: str
    priority: Literal["Regular", "Part-Time", "Extras"]
    rating: int = Field(ge=1, le=5)
    prefHrs: int
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
    preferredJobTypes: List[str]
    avoidedJobTypes: List[str]
    lovedByCompanies: List[CompanyRef]
    hatedByCompanies: List[CompanyRef]


# --- Limitation ---

class LimitationProfile(BaseModel):
    effectiveDate: str
    limitationInstructions: str


# --- softConstraints sub-models ---

class ConsecutiveShiftLimit(BaseModel):
    shiftType: str
    maxConsecutive: int
    timeUnit: str


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
    type: str
    clientName: Optional[str] = None
    shiftType: str
    dayOffset: int


class ConditionalConsequence(BaseModel):
    action: str
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
    vehicleType: str
    restrictionType: str


class InterpersonalConflict(BaseModel):
    conflictEmployeeName: str
    conflictType: str
    softConstraint: bool


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


# --- Full payload ---

class FullPayload(BaseModel):
    employee: EmployeeProfile
    limitation: LimitationProfile
    skills: List[str]
    softConstraints: SoftConstraints


# --- Validation report ---

class Discrepancy(BaseModel):
    field: str
    type: Literal["generated_only", "extractor_only", "divergent"]
    note: str


class ValidationReport(BaseModel):
    passed: bool
    confidence: Literal["high", "medium", "low"]
    discrepancies: List[Discrepancy]


# --- API request / response ---

class GenerateRequest(BaseModel):
    persona: str
    api_key: str


class BatchGenerateRequest(BaseModel):
    personas: Optional[List[str]] = None
    persona: Optional[str] = None
    count: int = Field(default=1, ge=1, le=20)
    api_key: str

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
