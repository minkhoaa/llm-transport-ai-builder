# Pipeline Upgrade — 3-Call CoT Design

## Goal

Eliminate hallucination in `softConstraints` generation, fix remaining hardcoded values in prompts and schemas, and restructure the generation prompt to be shorter and more focused using mandatory chain-of-thought.

## Architecture

Three sequential LLM calls per request, each with a single responsibility:

```
Call 1: Profile Generator
  Input:  persona name
  Output: _reasoning (stripped) + employee + skills + limitation.limitationInstructions
  Prompt: ~40% shorter than current, no softConstraints section

Call 2: Constraint Extractor (source of truth)
  Input:  limitationInstructions text from Call 1
  Output: softConstraints JSON
  Note:   This is the authoritative source — not a validator

Call 3: Quality Gate
  Input:  limitationInstructions + softConstraints from Call 2
  Output: { passed: bool, confidence: high|medium|low, issues: [str] }
  Note:   Natural language evaluation, replaces structured diff validator
```

Final payload is assembled by merging outputs from all three calls.

## Call 1 — Profile Generator Prompt Structure

Four focused sections, no softConstraints:

**Section 1 — Persona context** (~10 lines)
Describes only the requested persona + top-level rules (priority enum, rating enum, certification prefix, AM/PM logic, job type enum).

**Section 2 — Reference data** (lists only, no prose)
- Available skills and certifications
- Client registry (clientId + clientName)

**Section 3 — Chain-of-thought output format** (mandatory)
LLM must emit `_reasoning` as the first key, containing its decision rationale before filling any fields. `_reasoning` is parsed and discarded after validation — it never appears in the final API response.

Output JSON structure:
```json
{
  "_reasoning": {
    "schedule": "why AM/PM booleans are set this way",
    "skills": "which skills match this persona and why",
    "priority": "Regular/Part-Time/Extras and why",
    "limitation_plan": "which 2-3 constraints will appear and what phrases trigger them"
  },
  "employee": { ... },
  "skills": [ ... ],
  "limitation": {
    "limitationInstructions": "natural language text"
  }
}
```

**Section 4 — Hard rules** (~5 lines)
Only the non-negotiable constraints: enum values must match exactly, no invented clients, no overlap in job type lists.

## Call 2 — Constraint Extractor

Keeps the existing extraction prompt with minor fixes:
- Remove type annotations written as literal values in JSON schema (`int`, `float`, `bool`) — use example values instead
- Clarify that output must omit null/empty fields entirely

This call is now the **definitive source** of `softConstraints`. The generator (Call 1) is not asked to produce softConstraints at all.

## Call 3 — Quality Gate

New prompt. Reads the `limitationInstructions` text and `softConstraints` JSON together and evaluates:
- Are the extracted constraints actually supported by the text?
- Are there constraints in the text that were missed?
- Is the severity mapping correct (Must not → hard, Try not to → soft)?

Output:
```json
{
  "passed": true,
  "confidence": "high",
  "issues": []
}
```

Or on failure:
```json
{
  "passed": false,
  "confidence": "low",
  "issues": [
    "dailyTimeRestrictions found but text says 'Try not to start before 2pm' — should be soft, not hard",
    "crossDayDependencies present but no night shift mentioned in text"
  ]
}
```

## Schema Changes (`payload.py`)

### Add Literal validators to prevent free-text hallucination

| Field | Current | New |
|-------|---------|-----|
| `ConsecutiveShiftLimit.shiftType` | `str` | `Literal["evening", "morning", "night", "day", "any"]` |
| `ConsecutiveShiftLimit.timeUnit` | `str` | `Literal["shifts", "days"]` |
| `VehicleRestriction.vehicleType` | `str` | `Literal["truck", "van", "any"]` |
| `VehicleRestriction.restrictionType` | `str` | `Literal["no_day_and_night", "no_double", "cannot_drive"]` |
| `InterpersonalConflict.conflictType` | `str` | `Literal["cannot_work_together", "avoid_if_possible"]` |
| `ConditionalTrigger.type` | `str` | `Literal["job_assignment", "shift_scheduled", "day_of_week"]` |
| `ConditionalConsequence.action` | `str` | `Literal["cannot_assign", "requires_notice", "avoid_if_possible"]` |

### Replace `ValidationReport`

Current `discrepancies: List[Discrepancy]` (structured diff) → replaced with natural language:

```python
class ValidationReport(BaseModel):
    passed: bool
    confidence: Literal["high", "medium", "low"]
    issues: List[str]  # natural language descriptions from Call 3
```

`Discrepancy` model is removed.

## Prompt Hardcode Fixes

All in `generation_prompt.py`:

| Location | Problem | Fix |
|----------|---------|-----|
| softConstraints schema example | `"whitelistClients": ["CBE"]` — CBE not in registry | Remove; use actual clientName from registry in example |
| softConstraints schema example | `"allowedJobTypes": ["Residential"]` — not a valid type | Replace with `["MOV", "WH", "HHG"]` |
| softConstraints schema example | `"blacklist": ["Large Office Moving"]` — not a valid name | Remove this section (softConstraints no longer generated in Call 1) |
| output format example | AM/PM all false for AM, true for PM — hardcoded Night Owl pattern | Replace with descriptive comment |

Since Call 1 no longer outputs softConstraints, the softConstraints schema section (Section 6) is removed from the generation prompt entirely.

## File Map

| File | Change |
|------|--------|
| `src/generator/prompts/generation_prompt.py` | Rewrite: 4 sections, no softConstraints, CoT format |
| `src/generator/prompts/extraction_prompt.py` | Minor fixes: example values instead of type names |
| `src/generator/prompts/quality_prompt.py` | New file: quality gate prompt |
| `src/generator/persona_generator.py` | `generate()` becomes 3 sequential calls, strips `_reasoning` |
| `src/validator/constraint_validator.py` | Rework as `QualityGate`: calls Call 3, returns `ValidationReport` with `issues: List[str]` |
| `src/api/schemas/payload.py` | Add Literal validators; replace `Discrepancy` + `ValidationReport` |
| `src/services/builder_service.py` | Update to pass `softConstraints` from Call 2 into merged payload |

## Data Flow Detail

```python
# persona_generator.py — new generate() flow

# Call 1
raw1 = llm(GENERATION_SYSTEM_PROMPT, f"Generate profile for: {persona}")
data1 = json.loads(raw1)
reasoning = data1.pop("_reasoning", None)   # strip CoT, never exposed
partial = PartialPayload(**data1)             # employee + skills + limitation

# Call 2
raw2 = llm(EXTRACTION_SYSTEM_PROMPT, partial.limitation.limitationInstructions)
soft = SoftConstraints(**json.loads(raw2))

# Assemble full payload
payload = FullPayload(
    employee=partial.employee,
    limitation=partial.limitation,
    skills=partial.skills,
    softConstraints=soft,
)

# Call 3 (in QualityGate)
report = quality_gate.evaluate(
    limitation_instructions=partial.limitation.limitationInstructions,
    soft_constraints=soft,
)

return payload, report, attempts
```

## New Intermediate Schema

```python
class PartialPayload(BaseModel):
    """Output of Call 1 — no softConstraints."""
    employee: EmployeeProfile
    limitation: LimitationProfile
    skills: List[str]
```

## Retry Logic

- Call 1 retries up to 3 times on parse/validation failure (existing logic)
- Call 2 retries up to 2 times (extraction is simpler)
- Call 3 retries once on parse failure; on persistent failure returns `passed=False, confidence="low", issues=["Quality gate call failed"]`

## What Does NOT Change

- API surface (`/builder/generate`, `/builder/generate/batch`) — same request/response shape
- Provider routing (`PROVIDER_URLS`, `resolve_base_url`)
- `personalities` override (locked to selected persona)
- `effectiveDate` random generation
- `id` auto-increment
- UI (`static/index.html`) — no changes needed
- 9Router modal
