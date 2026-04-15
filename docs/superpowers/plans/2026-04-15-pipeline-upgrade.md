# Pipeline Upgrade — 3-Call CoT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single-LLM generation call into a 3-call chain-of-thought pipeline to eliminate hallucination in `softConstraints`, fix remaining hardcoded values in prompts, and replace the diff-based validator with a natural-language quality gate.

**Architecture:** Call 1 generates employee profile + limitationInstructions text (with CoT `_reasoning`, no softConstraints). Call 2 extracts softConstraints from that text (authoritative source). Call 3 is a natural-language quality gate checking alignment between text and extracted constraints. Final payload is assembled from all three outputs.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, OpenAI-compat client, loguru, pytest

**Spec:** `docs/superpowers/specs/2026-04-15-pipeline-upgrade-design.md`

---

## File Map

| File | Change |
|------|--------|
| `src/api/schemas/payload.py` | Add Literal validators; add `PartialLimitation`, `PartialPayload`; replace `Discrepancy`+`ValidationReport` |
| `src/generator/prompts/generation_prompt.py` | Rewrite: 4 sections, CoT `_reasoning`, no softConstraints |
| `src/generator/prompts/extraction_prompt.py` | Fix type annotations → example values |
| `src/generator/prompts/quality_prompt.py` | New file: quality gate prompt |
| `src/generator/persona_generator.py` | 3-call flow, strip `_reasoning`, assemble `FullPayload` |
| `src/validator/constraint_validator.py` | Replace `ConstraintValidator` with `QualityGate` |
| `src/services/builder_service.py` | `validator` → `quality_gate`, pass `softConstraints` from Call 2 |
| `src/api/routers/builder.py` | Instantiate `QualityGate` instead of `ConstraintValidator` |
| `tests/test_payload_schemas.py` | Test new Literal validators; new `ValidationReport` shape |
| `tests/test_persona_generator.py` | Mock 2 sequential API calls; update `VALID_CALL1` + `VALID_CALL2` fixtures |
| `tests/test_constraint_validator.py` | Rewrite for `QualityGate.evaluate()` |
| `tests/test_builder_service.py` | Use `quality_gate` kwarg; `issues=[]` not `discrepancies=[]` |

---

## Task 1: Update `src/api/schemas/payload.py`

**Files:**
- Modify: `src/api/schemas/payload.py`

### What changes
- Add `Literal` validators to 7 fields across 4 sub-models
- Add `PartialLimitation` and `PartialPayload` intermediate schemas (Call 1 output)
- Replace `Discrepancy` model and `ValidationReport.discrepancies` with `issues: List[str]`

- [ ] **Step 1: Run existing tests to confirm baseline passes**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests pass before any changes.

- [ ] **Step 2: Update the 4 sub-models with Literal types**

In `src/api/schemas/payload.py`, replace the 4 plain-`str` classes:

```python
class ConsecutiveShiftLimit(BaseModel):
    shiftType: Literal["evening", "morning", "night", "day", "any"]
    maxConsecutive: int
    timeUnit: Literal["shifts", "days"]


class ConditionalTrigger(BaseModel):
    type: Literal["job_assignment", "shift_scheduled", "day_of_week"]
    clientName: Optional[str] = None
    shiftType: str
    dayOffset: int


class ConditionalConsequence(BaseModel):
    action: Literal["cannot_assign", "requires_notice", "avoid_if_possible"]
    toShiftType: str
    onDayOffset: int


class VehicleRestriction(BaseModel):
    vehicleType: Literal["truck", "van", "any"]
    restrictionType: Literal["no_day_and_night", "no_double", "cannot_drive"]


class InterpersonalConflict(BaseModel):
    conflictEmployeeName: str
    conflictType: Literal["cannot_work_together", "avoid_if_possible"]
    softConstraint: bool
```

- [ ] **Step 3: Add `PartialLimitation` and `PartialPayload` after `LimitationProfile`**

Insert after `class LimitationProfile` in `src/api/schemas/payload.py`:

```python
# --- Intermediate schema (Call 1 output — no softConstraints, no effectiveDate) ---

class PartialLimitation(BaseModel):
    """Call 1 output: only the text, no effectiveDate (generated in code)."""
    limitationInstructions: str


class PartialPayload(BaseModel):
    """Output of Call 1 — no softConstraints."""
    employee: EmployeeProfile
    limitation: PartialLimitation
    skills: List[str]
```

- [ ] **Step 4: Replace `Discrepancy` + `ValidationReport`**

Remove:
```python
class Discrepancy(BaseModel):
    field: str
    type: Literal["generated_only", "extractor_only", "divergent"]
    note: str


class ValidationReport(BaseModel):
    passed: bool
    confidence: Literal["high", "medium", "low"]
    discrepancies: List[Discrepancy]
```

Replace with:
```python
class ValidationReport(BaseModel):
    passed: bool
    confidence: Literal["high", "medium", "low"]
    issues: List[str]  # natural language from Call 3
```

- [ ] **Step 5: Run tests to see which break (expected)**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected failures:
- `test_constraint_validator.py` — imports `Discrepancy`, tests `_diff`, `_build_report`
- `test_builder_service.py` — `ValidationReport(..., discrepancies=[])` no longer valid
- `test_persona_generator.py` — `VALID_PAYLOAD` has `softConstraints` (will still parse OK)

Record which tests break — they will be fixed in Task 8.

- [ ] **Step 6: Commit**

```bash
git add src/api/schemas/payload.py
git commit -m "feat(schemas): add Literal validators, PartialPayload, replace ValidationReport.discrepancies with issues"
```

---

## Task 2: Rewrite `src/generator/prompts/generation_prompt.py`

**Files:**
- Modify: `src/generator/prompts/generation_prompt.py`

### What changes
- Remove Section 6 (softConstraints schema) — Call 1 no longer generates constraints
- Add Section 3 (chain-of-thought `_reasoning` format as first key)
- Fix all hardcoded examples: CBE → real client name, Residential → MOV/WH/HHG, Large Office Moving → removed
- Replace hardcoded Night Owl AM/PM example with a descriptive comment
- Tighten the output schema to match `PartialPayload` (no `softConstraints` key)

- [ ] **Step 1: Rewrite the file**

Replace the entire contents of `src/generator/prompts/generation_prompt.py`:

```python
"""System prompt for LLM call #1: profile generator (no softConstraints)."""
from src.config.clients import CLIENTS as _CLIENTS

_CLIENT_TABLE = "\n".join(
    f'  - clientId: {c["clientId"]}, clientName: "{c["clientName"]}"'
    for c in _CLIENTS
)

GENERATION_SYSTEM_PROMPT = f"""\
You are an Expert Data Labeller for the AI Scheduler API.
Generate highly realistic, complex synthetic workforce JSON profiles.
Your output trains an LLM to handle real-world scheduling soft constraints.

## 1. CRITICAL RULES
- priority MUST be exactly "Regular", "Part-Time", or "Extras". NO exceptions.
- rating MUST be exactly one of: "1 - Poor", "2 - Needs Improvement", "3 - Standard", "4 - Above Average", "5 - Exceptional".
- Certifications MUST have the prefix "Certification (...)" e.g. "Certification (WHMIS)".
- Regular skills have NO prefix. Both go in the SAME skills array.
- personalities MUST be an array with EXACTLY ONE string: the exact persona name requested (e.g. ["Night Owl"]).
- AM/PM booleans MUST logically match the persona (Night Owl: all AM fields false, all PM fields true on weekdays).
- lovedByCompanies and hatedByCompanies MUST use ONLY clients from Section 2 below.
- preferredJobTypes and avoidedJobTypes MUST use ONLY these three values: "MOV", "WH", "HHG".
- preferredJobTypes and avoidedJobTypes MUST NOT overlap.
- limitationInstructions MUST mention 2-3 constraints using "Must not" (hard) or "Try not to" (soft).
- Do NOT output a softConstraints field — that is handled separately.

## 2. REFERENCE DATA

### Available Skills
Regular skills: Heavy Carry, Stair Carry, HHG, IT, Lead (2-8 ppl), Lead (9-15 ppl),
Lead (small deliveries), Supervisor (16-25 ppl), Truck Driver, Van Driver,
Installer (Basic), Installer (Standard), Installer (Advanced), Installer (Hanging),
Installer (New Furniture), Packer (Household), Packer (Commercial),
Whse 1 Helper, Whse 4 Helper, OMD Equip Repair

Certifications: Certification (WHMIS), Certification (Fall Arrest), Certification (CANA)

### Client Registry (ONLY use these for lovedByCompanies / hatedByCompanies)
{{_CLIENT_TABLE}}

## 3. CHAIN-OF-THOUGHT OUTPUT FORMAT
You MUST emit `_reasoning` as the FIRST key before any data fields.
`_reasoning` contains your decision rationale and is stripped before the response is returned.

Output JSON structure:
{{
  "_reasoning": {{
    "schedule": "why AM/PM booleans are set this way for this persona",
    "skills": "which skills match this persona and why",
    "priority": "Regular/Part-Time/Extras and why",
    "limitation_plan": "which 2-3 constraints will appear and what phrases trigger them"
  }},
  "employee": {{ ... }},
  "skills": [ ... ],
  "limitation": {{
    "limitationInstructions": "natural language text with Must not / Try not to"
  }}
}}

## 4. HARD RULES
- priority enum must match exactly: Regular | Part-Time | Extras
- rating enum must match exactly: 1 - Poor | 2 - Needs Improvement | 3 - Standard | 4 - Above Average | 5 - Exceptional
- Certification prefix is mandatory: "Certification (WHMIS)" not "WHMIS"
- No invented clients — lovedByCompanies/hatedByCompanies only from Section 2
- preferredJobTypes and avoidedJobTypes must not overlap
- Output ONLY valid JSON (no markdown, no explanation outside JSON)

## 5. THE 27 PERSONA DICTIONARY
1. Veteran Lead: High performer, crew chief, company face.
2. Senior worker: Highly paid, advanced skills, specialized, trainer.
3. Family-First Parent: Has kids, avoids school pickups, kids activities.
4. Caregiver of aging parents: Unpredictable emergencies, parent appointments.
5. Religious catholic worker: Sabbath/Friday prayers off.
6. Part-Time Student: Avoids class schedule, basic skills, needs training.
7. Night Owl: Prefers nights, bad performance mornings.
8. Early Bird: Wants mornings only, goes to bed at 9pm.
9. Weekend Warrior: Has weekday job elsewhere.
10. Cranky Old-Timer: Opinionated, doesn't get along with certain people.
11. Pair bonded: Works best with some partners at some jobs.
12. Injury-Returning Worker: Serious injury, light duty only.
13. New Hire (Probationary): Just came, do not lead, follow only, needs driving assistance.
14. Safety Champion: Heavy skills, complicated certifications.
15. Regional Road Warrior: Long-haul, willing to travel/stay overnight.
16. Master Packer: Fragile/HHG specialist, white-glove service.
17. Night School Student: Evening classes, works mostly days.
18. Volunteer: Suddenly appears and disappears, can do many work variants.
19. Gym Fanatic: Morning/evening workouts must be respected, can lift heavy.
20. Injury-Returning (Back): Back injury, light duty only.
21. Injury-Returning (Knee): Knee surgery, no stairs/lifting.
22. Diabetic (Meal Timing): Needs regular meal breaks, predictable hours.
23. Chronic Fatigue: Cannot do long/consecutive shifts, must give advance notice.
24. Allergy-Restricted: Chemical/dust allergies, cannot go to certain sites.
25. Eager Rookie: No skills but says yes to everything, needs constant supervision.
26. Summer Help: Seasonal student, can only work certain months.
27. Apprentice: Must always be paired with a mentor.

## 6. FULL OUTPUT EXAMPLE
Output ONLY valid JSON. Schema:
{{
  "_reasoning": {{
    "schedule": "Night Owl avoids mornings — all AM fields false, PM fields true on weekdays",
    "skills": "Experienced enough for Truck Driver and Heavy Carry",
    "priority": "Regular — full-time availability",
    "limitation_plan": "dailyTimeRestrictions (start after 2pm), consecutiveShiftLimits (max 3 night shifts)"
  }},
  "employee": {{
    "id": null,
    "name": "[realistic full name]",
    "priority": "Regular",
    "rating": "3 - Standard",
    "prefHrs": 35,
    "mondayAm": false, "mondayPm": true,
    "tuesdayAm": false, "tuesdayPm": true,
    "wednesdayAm": false, "wednesdayPm": true,
    "thursdayAm": false, "thursdayPm": true,
    "fridayAm": false, "fridayPm": true,
    "saturdayAm": false, "saturdayPm": false,
    "sundayAm": false, "sundayPm": false,
    "personalities": ["Night Owl"],
    "additionalNotes": "[realistic edge-case note]",
    "preferredJobTypes": ["WH"],
    "avoidedJobTypes": ["MOV"],
    "lovedByCompanies": [{{{"clientId": 22, "clientName": "University of Calgary"}}}],
    "hatedByCompanies": []
  }},
  "skills": ["Truck Driver", "Heavy Carry"],
  "limitation": {{
    "limitationInstructions": "Must not start any shift before 14:00. Try not to schedule more than 3 consecutive night shifts."
  }}
}}
"""
```

- [ ] **Step 2: Verify import still works**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
python -c "from src.generator.prompts.generation_prompt import GENERATION_SYSTEM_PROMPT; print('OK', len(GENERATION_SYSTEM_PROMPT), 'chars')"
```
Expected: prints `OK <number> chars` with no error.

- [ ] **Step 3: Commit**

```bash
git add src/generator/prompts/generation_prompt.py
git commit -m "feat(prompts): rewrite generation prompt — 4 sections, CoT _reasoning, no softConstraints"
```

---

## Task 3: Fix `src/generator/prompts/extraction_prompt.py`

**Files:**
- Modify: `src/generator/prompts/extraction_prompt.py`

### What changes
Replace type-annotation literals (`int`, `float`, `bool`) with concrete example values so the LLM sees valid JSON, not pseudo-code. Also add the clarification that null/empty fields must be omitted.

- [ ] **Step 1: Replace the file contents**

```python
"""System prompt for LLM call #2: constraint extractor (authoritative source of softConstraints)."""

EXTRACTION_SYSTEM_PROMPT = """\
You are a scheduling constraint extractor.
Given a limitationInstructions text, extract ALL softConstraints as a JSON object.
This is the authoritative source — extract everything the text implies, do not skip anything.

Output ONLY valid JSON. Omit null and empty fields entirely — do not include them.

Example structure (omit any field not applicable):
{
  "consecutiveShiftLimits": [{"shiftType": "night", "maxConsecutive": 3, "timeUnit": "shifts"}],
  "dailyTimeRestrictions": {"startTimeAfter": "14:00", "endTimeBefore": "22:00", "maxDailyHours": 8.0, "appliesToDays": ["monday", "tuesday"]},
  "recurringTimeOffPatterns": [{"pattern": "every_other", "timeUnit": "week", "appliesToDays": ["saturday"], "startWeekUnknown": true}],
  "crossDayDependencies": [{"ifShift": "evening", "thenCannotWork": "morning", "nextDayOffset": 1}],
  "weeklyFrequencyLimits": [{"shiftType": "night", "maxPerWeek": 2}],
  "conditionalRestrictions": [{"trigger": {"type": "job_assignment", "clientName": "Alberta Health Services", "shiftType": "any", "dayOffset": 0}, "consequence": {"action": "cannot_assign", "toShiftType": "night", "onDayOffset": 0}, "originalPhrase": "Must not work nights when assigned to AHS"}],
  "advanceNoticeRequired": [{"shiftType": "weekend", "daysRequired": 3, "ambiguous": false}],
  "crewSizeRestrictions": {"minCrewSize": 2, "maxCrewSize": 6, "allowedSizes": null, "appliesToLeadershipOnly": false},
  "leadershipRestrictions": [{"maxCrewSize": 8, "allowedJobTypes": ["MOV", "WH"], "entityResolutionRequired": false}],
  "jobTypeRestrictions": {"whitelist": null, "blacklist": ["HHG"], "whitelistClients": null, "blacklistClients": null, "entityResolutionRequired": false},
  "vehicleRestrictions": [{"vehicleType": "truck", "restrictionType": "cannot_drive"}],
  "interpersonalConflicts": [{"conflictEmployeeName": "John Smith", "conflictType": "cannot_work_together", "softConstraint": false}]
}

Rules:
- Extract ONLY what is clearly stated in the text.
- "Must not" / "Never" -> hard constraint (softConstraint: false where applicable).
- "Try not to" -> soft constraint (softConstraint: true where applicable).
- Do not invent constraints not present in the text.
- Omit null and empty arrays/objects — do not include them in the output at all.
"""
```

- [ ] **Step 2: Verify import**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
python -c "from src.generator.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/generator/prompts/extraction_prompt.py
git commit -m "fix(prompts): replace type annotations with example values in extraction prompt"
```

---

## Task 4: Create `src/generator/prompts/quality_prompt.py`

**Files:**
- Create: `src/generator/prompts/quality_prompt.py`

### What changes
New file: quality gate system prompt for Call 3. Takes `limitationInstructions` text and `softConstraints` JSON, returns `{passed, confidence, issues}`.

- [ ] **Step 1: Create the file**

```python
"""System prompt for LLM call #3: quality gate."""

QUALITY_SYSTEM_PROMPT = """\
You are a scheduling constraint quality reviewer.
You receive two inputs:
1. A `limitationInstructions` text written in natural language.
2. A `softConstraints` JSON object extracted from that text.

Your job is to evaluate whether the extracted constraints faithfully represent the text.

Check for:
- Constraints in the text that were NOT extracted (missed constraints)
- Constraints in the JSON that are NOT supported by the text (invented constraints)
- Wrong severity mapping: "Must not" / "Never" should be hard; "Try not to" should be soft
- Wrong field values (e.g. wrong shift type, wrong day, wrong limit number)

Output ONLY valid JSON:
{
  "passed": true,
  "confidence": "high",
  "issues": []
}

Or if there are problems:
{
  "passed": false,
  "confidence": "low",
  "issues": [
    "dailyTimeRestrictions.startTimeAfter is 09:00 but text says 'Must not start before 2pm' — should be 14:00",
    "crossDayDependencies present but text mentions no night shift carry-over"
  ]
}

Confidence levels:
- "high": you are confident all constraints are correctly extracted with no errors
- "medium": minor ambiguity or 1 small issue you are uncertain about
- "low": clear errors, missed constraints, or invented constraints

`passed` is true only when there are zero issues.
Output ONLY the JSON — no markdown, no explanation.
"""
```

- [ ] **Step 2: Verify import**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
python -c "from src.generator.prompts.quality_prompt import QUALITY_SYSTEM_PROMPT; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/generator/prompts/quality_prompt.py
git commit -m "feat(prompts): add quality gate prompt for Call 3"
```

---

## Task 5: Rewrite `src/generator/persona_generator.py`

**Files:**
- Modify: `src/generator/persona_generator.py`

### What changes
- `generate()` becomes a 3-call flow: Call 1 → Call 2 → assemble → return
- `_reasoning` is stripped via `data1.pop("_reasoning", None)` before `PartialPayload` parsing
- Call 1 parses into `PartialPayload` (uses `PartialLimitation` — no `effectiveDate`)
- Call 2 parses into `SoftConstraints`
- Assembly builds `FullPayload` with `LimitationProfile(effectiveDate=_random_future_date(), limitationInstructions=...)`
- `personalities` is locked after Call 1 parse: `partial.employee.personalities = [persona]`
- Return signature changes from `(FullPayload, int)` to `(FullPayload, SoftConstraints, int)` — service needs `SoftConstraints` separately to pass to QualityGate
- Call 1 retries up to `max_retries` (default 3); Call 2 retries up to 2 times

- [ ] **Step 1: Rewrite the file**

```python
"""PersonaGenerator: validates persona name and drives the 3-call pipeline."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import FullPayload, LimitationProfile, PartialPayload, SoftConstraints
from src.config.llm_config import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_MODEL,
    EXTRACTION_TEMPERATURE,
    GENERATION_MAX_TOKENS,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    create_client,
)
from src.generator.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT
from src.generator.prompts.generation_prompt import GENERATION_SYSTEM_PROMPT

VALID_PERSONAS = [
    "Veteran Lead", "Senior worker", "Family-First Parent",
    "Caregiver of aging parents", "Religious catholic worker",
    "Part-Time Student", "Night Owl", "Early Bird", "Weekend Warrior",
    "Cranky Old-Timer", "Pair bonded", "Injury-Returning Worker",
    "New Hire (Probationary)", "Safety Champion", "Regional Road Warrior",
    "Master Packer", "Night School Student", "Volunteer", "Gym Fanatic",
    "Injury-Returning (Back)", "Injury-Returning (Knee)",
    "Diabetic (Meal Timing)", "Chronic Fatigue", "Allergy-Restricted",
    "Eager Rookie", "Summer Help", "Apprentice",
]


def _random_future_date() -> str:
    """Return a random future date between 1 week and 18 months from today."""
    today = date.today()
    days_ahead = random.randint(7, 548)
    return (today + timedelta(days=days_ahead)).isoformat()


class InvalidPersonaError(ValueError):
    pass


class GenerationError(RuntimeError):
    pass


class PersonaGenerator:
    def validate_persona(self, persona: str) -> None:
        if persona not in VALID_PERSONAS:
            raise InvalidPersonaError(
                f"Unknown persona '{persona}'. Valid personas: {VALID_PERSONAS}"
            )

    def generate(
        self,
        persona: str,
        api_key: str,
        *,
        base_url: str = "",
        model: str = "",
        max_retries: int = 3,
    ) -> tuple[FullPayload, SoftConstraints, int]:
        """Run 3-call pipeline. Returns (full_payload, soft_constraints, attempts_used)."""
        client = create_client(api_key, base_url)
        gen_model = model or GENERATION_MODEL
        ext_model = model or EXTRACTION_MODEL

        # --- Call 1: Profile generator ---
        last_error: str | None = None
        partial: PartialPayload | None = None

        for attempt in range(1, max_retries + 1):
            if last_error and attempt > 1:
                messages = [
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Generate profile for: {persona}"},
                    {"role": "assistant", "content": "I will retry with a corrected response."},
                    {
                        "role": "user",
                        "content": (
                            f"Your previous output was invalid. Error: {last_error}\n"
                            "Please fix it and output valid JSON exactly matching the schema."
                        ),
                    },
                ]
            else:
                messages = [
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Generate profile for: {persona}"},
                ]

            logger.debug(f"Call 1 attempt {attempt}/{max_retries} for '{persona}'")
            response = client.chat.completions.create(
                model=gen_model,
                messages=messages,
                temperature=GENERATION_TEMPERATURE,
                max_tokens=GENERATION_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw1 = response.choices[0].message.content

            try:
                data1 = json.loads(raw1)
                data1.pop("_reasoning", None)  # strip CoT — never exposed
                partial = PartialPayload(**data1)
                partial.employee.personalities = [persona]  # lock to selected persona
                break
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                last_error = str(exc)
                logger.warning(f"Call 1 attempt {attempt} failed: {last_error}")
        else:
            raise GenerationError(
                f"Call 1 failed for '{persona}' after {max_retries} attempts. "
                f"Last error: {last_error}"
            )

        attempts_used = attempt

        # --- Call 2: Constraint extractor ---
        soft: SoftConstraints | None = None
        for ext_attempt in range(1, 3):  # up to 2 retries
            logger.debug(f"Call 2 attempt {ext_attempt}/2 for '{persona}'")
            response2 = client.chat.completions.create(
                model=ext_model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": partial.limitation.limitationInstructions},
                ],
                temperature=EXTRACTION_TEMPERATURE,
                max_tokens=EXTRACTION_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw2 = response2.choices[0].message.content
            try:
                soft = SoftConstraints(**json.loads(raw2))
                break
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                logger.warning(f"Call 2 attempt {ext_attempt} failed: {exc}")
                if ext_attempt == 2:
                    logger.warning("Call 2 exhausted retries — using empty SoftConstraints")
                    soft = SoftConstraints()

        # --- Assemble full payload ---
        payload = FullPayload(
            employee=partial.employee,
            limitation=LimitationProfile(
                effectiveDate=_random_future_date(),
                limitationInstructions=partial.limitation.limitationInstructions,
            ),
            skills=partial.skills,
            softConstraints=soft,
        )

        return payload, soft, attempts_used
```

- [ ] **Step 2: Verify import compiles**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
python -c "from src.generator.persona_generator import PersonaGenerator; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/generator/persona_generator.py
git commit -m "feat(generator): 3-call pipeline — Call 1 profile, Call 2 extraction, strip _reasoning"
```

---

## Task 6: Replace `ConstraintValidator` with `QualityGate`

**Files:**
- Modify: `src/validator/constraint_validator.py`

### What changes
- Delete all existing logic (`_diff`, `_build_report`, `ConstraintValidator`)
- New `QualityGate` class with single method `evaluate()`
- Calls LLM with `QUALITY_SYSTEM_PROMPT`; user message is JSON with both inputs
- On parse failure returns `passed=False, confidence="low", issues=["Quality gate call failed: ..."]`

- [ ] **Step 1: Rewrite the file**

```python
"""QualityGate: LLM call #3 — natural language evaluation of extracted constraints."""
from __future__ import annotations

import json

from loguru import logger
from pydantic import ValidationError

from src.api.schemas.payload import SoftConstraints, ValidationReport
from src.config.llm_config import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_MODEL,
    EXTRACTION_TEMPERATURE,
    create_client,
)
from src.generator.prompts.quality_prompt import QUALITY_SYSTEM_PROMPT


class QualityGate:
    def evaluate(
        self,
        limitation_instructions: str,
        soft_constraints: SoftConstraints,
        api_key: str,
        base_url: str = "",
        model: str = "",
    ) -> ValidationReport:
        """Call LLM to evaluate alignment between limitation text and extracted constraints."""
        client = create_client(api_key, base_url)
        effective_model = model or EXTRACTION_MODEL

        user_message = json.dumps(
            {
                "limitationInstructions": limitation_instructions,
                "softConstraints": soft_constraints.model_dump(),
            },
            indent=2,
        )

        # Retry once on parse failure
        for attempt in range(1, 3):
            try:
                response = client.chat.completions.create(
                    model=effective_model,
                    messages=[
                        {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=EXTRACTION_TEMPERATURE,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                data = json.loads(raw)
                return ValidationReport(**data)
            except (json.JSONDecodeError, ValidationError, Exception) as exc:
                logger.warning(f"QualityGate attempt {attempt} failed: {exc}")

        return ValidationReport(
            passed=False,
            confidence="low",
            issues=["Quality gate call failed after 2 attempts"],
        )
```

- [ ] **Step 2: Verify import**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
python -c "from src.validator.constraint_validator import QualityGate; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/validator/constraint_validator.py
git commit -m "feat(validator): replace ConstraintValidator with QualityGate (Call 3, natural language)"
```

---

## Task 7: Update `BuilderService` and router

**Files:**
- Modify: `src/services/builder_service.py`
- Modify: `src/api/routers/builder.py`

### What changes
- `BuilderService.__init__` takes `quality_gate: QualityGate` instead of `validator: ConstraintValidator`
- `generate_single` unpacks 3-tuple `(payload, soft, attempts)` from `generator.generate()`
- Calls `quality_gate.evaluate(limitation_instructions, soft, api_key, base_url, model)`
- Router imports `QualityGate` instead of `ConstraintValidator`

- [ ] **Step 1: Rewrite `src/services/builder_service.py`**

```python
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
        self, persona: str, api_key: str, base_url: str = "", model: str = ""
    ) -> GenerateResponse:
        self._generator.validate_persona(persona)
        payload, soft, attempts = self._generator.generate(
            persona, api_key, base_url=base_url, model=model
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

        for persona in personas:
            try:
                response = self.generate_single(persona, request.api_key, base_url, model)
                profiles.append(response)
            except Exception as exc:
                logger.warning(f"Batch generation failed for '{persona}': {exc}")
                failed += 1

        return BatchGenerateResponse(total=len(personas), failed=failed, profiles=profiles)
```

- [ ] **Step 2: Update `src/api/routers/builder.py`**

Change the import and instantiation lines. Find:

```python
from src.validator.constraint_validator import ConstraintValidator

router = APIRouter(prefix="/builder", tags=["builder"])

_generator = PersonaGenerator()
_validator = ConstraintValidator()
_service = BuilderService(generator=_generator, validator=_validator)
```

Replace with:

```python
from src.validator.constraint_validator import QualityGate

router = APIRouter(prefix="/builder", tags=["builder"])

_generator = PersonaGenerator()
_quality_gate = QualityGate()
_service = BuilderService(generator=_generator, quality_gate=_quality_gate)
```

- [ ] **Step 3: Verify imports compile**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
python -c "from src.services.builder_service import BuilderService; print('OK')"
python -c "from src.api.routers.builder import router; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add src/services/builder_service.py src/api/routers/builder.py
git commit -m "feat(service): wire QualityGate into BuilderService, unpack 3-tuple from generator"
```

---

## Task 8: Update all 4 test files

**Files:**
- Modify: `tests/test_payload_schemas.py`
- Modify: `tests/test_persona_generator.py`
- Modify: `tests/test_constraint_validator.py`
- Modify: `tests/test_builder_service.py`

### What changes
Bring all tests back to green after schema and implementation changes.

- [ ] **Step 1: Read current `tests/test_payload_schemas.py` and update**

The existing tests still work for `EmployeeProfile` and `BatchGenerateRequest`.
Add tests for the new Literal validators and the new `ValidationReport.issues` field.
The file already has tests that pass — append new ones:

```python
# Add at end of tests/test_payload_schemas.py:

from src.api.schemas.payload import (
    ConsecutiveShiftLimit,
    VehicleRestriction,
    InterpersonalConflict,
    ConditionalTrigger,
    ConditionalConsequence,
    ValidationReport,
    PartialLimitation,
    PartialPayload,
)


def test_consecutive_shift_limit_valid_shift_type():
    c = ConsecutiveShiftLimit(shiftType="night", maxConsecutive=3, timeUnit="shifts")
    assert c.shiftType == "night"


def test_consecutive_shift_limit_invalid_shift_type():
    with pytest.raises(ValidationError):
        ConsecutiveShiftLimit(shiftType="graveyard", maxConsecutive=3, timeUnit="shifts")


def test_vehicle_restriction_valid():
    v = VehicleRestriction(vehicleType="truck", restrictionType="cannot_drive")
    assert v.vehicleType == "truck"


def test_vehicle_restriction_invalid():
    with pytest.raises(ValidationError):
        VehicleRestriction(vehicleType="bicycle", restrictionType="cannot_drive")


def test_interpersonal_conflict_valid():
    ic = InterpersonalConflict(
        conflictEmployeeName="John",
        conflictType="cannot_work_together",
        softConstraint=False,
    )
    assert ic.conflictType == "cannot_work_together"


def test_interpersonal_conflict_invalid():
    with pytest.raises(ValidationError):
        InterpersonalConflict(
            conflictEmployeeName="John",
            conflictType="enemies",
            softConstraint=False,
        )


def test_validation_report_has_issues_not_discrepancies():
    r = ValidationReport(passed=True, confidence="high", issues=[])
    assert r.issues == []
    assert not hasattr(r, "discrepancies")


def test_partial_limitation_no_effective_date():
    pl = PartialLimitation(limitationInstructions="Must not start before 14:00.")
    assert pl.limitationInstructions == "Must not start before 14:00."
    assert not hasattr(pl, "effectiveDate")


def test_partial_payload_no_soft_constraints(make_employee):
    pp = PartialPayload(
        employee=EmployeeProfile(**make_employee()),
        limitation=PartialLimitation(limitationInstructions="Try not to work nights."),
        skills=["Heavy Carry"],
    )
    assert not hasattr(pp, "softConstraints")
```

Note: The `make_employee` fixture needs to be converted to a pytest fixture. Find the existing `make_employee` function in the file and add `@pytest.fixture` decorator, OR keep it as a plain function and call it directly.

Actual change: The existing `make_employee` is a plain function — keep it as is. The last test above should call `PartialPayload(employee=EmployeeProfile(**make_employee()), ...)` without the fixture syntax. Remove `make_employee` from the parameter list:

```python
def test_partial_payload_no_soft_constraints():
    pp = PartialPayload(
        employee=EmployeeProfile(**make_employee()),
        limitation=PartialLimitation(limitationInstructions="Try not to work nights."),
        skills=["Heavy Carry"],
    )
    assert not hasattr(pp, "softConstraints")
```

- [ ] **Step 2: Rewrite `tests/test_constraint_validator.py`**

Completely replace file contents:

```python
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


def test_evaluate_includes_soft_constraints_in_user_message():
    """Verify the user message sent to LLM contains both inputs."""
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
```

- [ ] **Step 3: Rewrite `tests/test_persona_generator.py`**

The generator now makes 2 LLM calls per attempt. Call 1 returns a `PartialPayload`-compatible dict (no `softConstraints`). Call 2 returns a `SoftConstraints`-compatible dict.

The `mock_client.chat.completions.create` must have 2 entries in `side_effect` per successful generation (1 per call).

Replace file contents:

```python
import json
from unittest.mock import MagicMock, patch

import pytest

from src.generator.persona_generator import (
    GenerationError,
    InvalidPersonaError,
    PersonaGenerator,
    VALID_PERSONAS,
)

# Call 1 output: PartialPayload-compatible (no softConstraints, no effectiveDate)
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
    # Call 1 then Call 2
    mock_client.chat.completions.create.side_effect = [
        _make_response(json.dumps(VALID_CALL1)),
        _make_response(json.dumps(VALID_CALL2)),
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
    # _reasoning must not appear anywhere in the final payload
    payload_dict = payload.model_dump()
    assert "_reasoning" not in payload_dict
    assert "_reasoning" not in payload_dict.get("employee", {})


def test_generate_retries_call1_on_invalid_json():
    gen = PersonaGenerator()
    mock_client = MagicMock()
    # First Call 1 attempt: bad JSON. Second Call 1: good. Then Call 2.
    mock_client.chat.completions.create.side_effect = [
        _make_response("not json"),              # Call 1 attempt 1 — fail
        _make_response(json.dumps(VALID_CALL1)), # Call 1 attempt 2 — success
        _make_response(json.dumps(VALID_CALL2)), # Call 2
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
        _make_response(json.dumps(VALID_CALL1)), # Call 1 — success
        _make_response("bad json"),              # Call 2 attempt 1 — fail
        _make_response("bad json"),              # Call 2 attempt 2 — fail
    ]
    with patch("src.generator.persona_generator.create_client", return_value=mock_client):
        payload, soft, attempts = gen.generate("Night Owl", "fake_key")
    # Falls back to empty SoftConstraints rather than raising
    assert isinstance(soft, SoftConstraints)
    assert soft.dailyTimeRestrictions is None
```

- [ ] **Step 4: Update `tests/test_builder_service.py`**

Three changes:
1. `ValidationReport(..., discrepancies=[])` → `ValidationReport(..., issues=[])`
2. `BuilderService(generator=gen, validator=val)` → `BuilderService(generator=gen, quality_gate=qg)`
3. `val.validate.return_value` → `qg.evaluate.return_value`
4. `gen.generate.return_value = (_make_payload(), 1)` → `gen.generate.return_value = (_make_payload(), SoftConstraints(), 1)` (3-tuple)

Replace entire file:

```python
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
            name="Test User", priority="Regular", rating="3 - Standard", prefHrs=40,
            mondayAm=True, mondayPm=True, tuesdayAm=True, tuesdayPm=True,
            wednesdayAm=True, wednesdayPm=True, thursdayAm=True, thursdayPm=True,
            fridayAm=True, fridayPm=True, saturdayAm=False, saturdayPm=False,
            sundayAm=False, sundayPm=False,
            personalities=["Test"], additionalNotes="",
            preferredJobTypes=[], avoidedJobTypes=[],
            lovedByCompanies=[], hatedByCompanies=[],
        ),
        limitation=LimitationProfile(
            effectiveDate="2026-05-01",
            limitationInstructions="Must not work nights.",
        ),
        skills=[],
        softConstraints=SoftConstraints(),
    )


def _make_report(passed=True):
    return ValidationReport(passed=passed, confidence="high", issues=[])


def test_generate_single_returns_response():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.return_value = (_make_payload(), SoftConstraints(), 1)
    qg = MagicMock()
    qg.evaluate.return_value = _make_report()

    service = BuilderService(generator=gen, quality_gate=qg)
    response = service.generate_single("Night Owl", "fake_key")

    assert isinstance(response, GenerateResponse)
    assert response.persona == "Night Owl"
    assert response.attempts == 1


def test_generate_single_raises_on_invalid_persona():
    gen = MagicMock()
    gen.validate_persona.side_effect = InvalidPersonaError("Unknown")
    service = BuilderService(generator=gen, quality_gate=MagicMock())

    with pytest.raises(InvalidPersonaError):
        service.generate_single("Pirate", "fake_key")


def test_generate_batch_with_persona_and_count():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.return_value = (_make_payload(), SoftConstraints(), 1)
    qg = MagicMock()
    qg.evaluate.return_value = _make_report()

    service = BuilderService(generator=gen, quality_gate=qg)
    request = BatchGenerateRequest(persona="Night Owl", count=3, api_key="fake")
    response = service.generate_batch(request)

    assert response.total == 3
    assert response.failed == 0
    assert len(response.profiles) == 3


def test_generate_batch_with_explicit_personas():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.return_value = (_make_payload(), SoftConstraints(), 1)
    qg = MagicMock()
    qg.evaluate.return_value = _make_report()

    service = BuilderService(generator=gen, quality_gate=qg)
    request = BatchGenerateRequest(personas=["Night Owl", "Early Bird"], api_key="fake")
    response = service.generate_batch(request)

    assert response.total == 2
    assert len(response.profiles) == 2


def test_generate_batch_partial_failure():
    gen = MagicMock()
    gen.validate_persona.return_value = None
    gen.generate.side_effect = [(_make_payload(), SoftConstraints(), 1), GenerationError("failed")]
    qg = MagicMock()
    qg.evaluate.return_value = _make_report()

    service = BuilderService(generator=gen, quality_gate=qg)
    request = BatchGenerateRequest(personas=["Night Owl", "Early Bird"], api_key="fake")
    response = service.generate_batch(request)

    assert response.total == 2
    assert response.failed == 1
    assert len(response.profiles) == 1
```

- [ ] **Step 5: Run all tests and confirm green**

```bash
cd /home/khoa/Projects/labelling/llm-transport-ai-builder
pytest tests/ -v --tb=short
```
Expected: all tests pass. If any fail, fix them before committing.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: update all test files for 3-call pipeline and QualityGate"
```

---

## Self-Review

### Spec coverage check
| Spec requirement | Covered by |
|---|---|
| Call 1: no softConstraints, CoT `_reasoning` | Task 2 (prompt), Task 5 (generator) |
| Call 2: authoritative softConstraints source | Task 3 (prompt fix), Task 5 (generator Call 2) |
| Call 3: natural language quality gate | Task 4 (prompt), Task 6 (QualityGate) |
| `PartialPayload` + `PartialLimitation` schemas | Task 1 |
| Literal validators on 7 fields | Task 1 |
| `ValidationReport.issues: List[str]` replaces `discrepancies` | Task 1 |
| `Discrepancy` model removed | Task 1 |
| `_reasoning` stripped, never in response | Task 5 |
| `personalities` locked to selected persona | Task 5 |
| `effectiveDate` generated in code, not by LLM | Task 5 |
| Call 1 retries up to 3x, Call 2 up to 2x | Task 5 |
| Call 3 retries once, fallback on failure | Task 6 |
| API surface unchanged | No router endpoint changes (only internals) |
| Builder service wires QualityGate | Task 7 |
| All tests updated | Task 8 |

### Type consistency check
- `PersonaGenerator.generate()` returns `tuple[FullPayload, SoftConstraints, int]` — matched in Task 7 (`payload, soft, attempts = ...`)
- `QualityGate.evaluate()` takes `soft_constraints: SoftConstraints` — matched in Task 7
- `ValidationReport.issues: List[str]` — used correctly in Task 8 (`issues=[]`)
- `PartialPayload.limitation` is `PartialLimitation` (has only `limitationInstructions`) — `persona_generator.py` accesses `partial.limitation.limitationInstructions` ✓
- `BuilderService.__init__` takes `quality_gate: QualityGate` — router in Task 7 passes `quality_gate=_quality_gate` ✓
