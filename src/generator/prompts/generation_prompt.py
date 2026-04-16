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
- prefHrs MUST be consistent with AM/PM availability: each true AM or PM slot ≈ 5 hours capacity.
  A worker with only 2 true slots can work at most 10h/week — prefHrs must not exceed slots × 5.
  Examples: 2 slots → prefHrs ≤ 10 | 5 slots → prefHrs ≤ 25 | 8 slots → prefHrs ≤ 40 | 14 slots → prefHrs ≤ 70.
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
7. Night Owl: Prefers nights, bad performance mornings. limitationInstructions must describe ADDITIONAL constraints (e.g. max consecutive night shifts, cross-day dependencies after nights) — do NOT write "no morning shifts" or "no weekend shifts" since those are already expressed by the false AM/PM booleans.
8. Early Bird: Wants mornings only, goes to bed at 9pm. limitationInstructions MUST use endTimeBefore (e.g. "Must not schedule any shift that ends after 12:00") to express the morning-only constraint — do NOT write "must not start after HH:MM" (that semantically inverts the schema field).
9. Weekend Warrior: Has weekday job elsewhere. limitationInstructions must use simple schema-mappable constraints such as dailyTimeRestrictions (max hours per day on weekends), weeklyFrequencyLimits (max shifts per week), or crossDayDependencies — do NOT write multi-condition rules like "crews larger than N without advance notice".
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
20. Injury-Returning (Back): Back injury, light duty only. limitationInstructions must include physical restrictions (no heavy lifting, no stair carries).
21. Injury-Returning (Knee): Knee surgery, no stairs/lifting. limitationInstructions must include physical restrictions (no stair carries, no heavy equipment).
22. Diabetic (Meal Timing): Needs regular meal breaks, predictable hours. limitationInstructions must use direct time constraints (e.g. "Must not schedule any shift longer than 5 hours", "Must not schedule shifts that start before 08:00 or end after 18:00") — do NOT write "without a break" or break-interval language.
23. Chronic Fatigue: Cannot do long/consecutive shifts, must give advance notice.
24. Allergy-Restricted: Chemical/dust allergies, cannot go to certain sites. limitationInstructions must phrase restrictions as environment types (e.g. "chemical environments", "dusty sites", "sites with heavy dust or chemical exposure") — do NOT list specific substances like spray paint or adhesives.
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
    "lovedByCompanies": [{{"clientId": 22, "clientName": "University of Calgary"}}],
    "hatedByCompanies": []
  }},
  "skills": ["Truck Driver", "Heavy Carry"],
  "limitation": {{
    "limitationInstructions": "Must not start any shift before 14:00. Try not to schedule more than 3 consecutive night shifts."
  }}
}}
"""
