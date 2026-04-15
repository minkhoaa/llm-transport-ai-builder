"""System prompt for LLM call #1: full payload generation."""
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
- Certifications MUST have the prefix "Certification (...)" e.g. "Certification (WHMIS)".
- Regular skills have NO prefix. Both go in the SAME skills array.
- personalities is an ARRAY of strings (e.g. ["Night Owl", "Late starter"]).
- For hard constraints use "Must not" or "Never"; for soft constraints use "Try not to".
- AM/PM booleans MUST logically match the persona (Night Owl: all AM fields false).
- lovedByCompanies and hatedByCompanies MUST use ONLY clients from Section 5 below.
- preferredJobTypes and avoidedJobTypes MUST use ONLY these three values: "MOV", "WH", "HHG". NO other strings.
- preferredJobTypes and avoidedJobTypes MUST NOT overlap (same value cannot appear in both).
- The softConstraints you output MUST directly reflect the limitationInstructions text.

## 2. THE 27 PERSONA DICTIONARY
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

## 3. THE 11 SOFT CONSTRAINTS (trigger 2-3 in limitationInstructions)
1. dailyTimeRestrictions: Max hours, start after, or end before a time.
2. recurringTimeOffPatterns: Scheduled predictable off-time (e.g. every Saturday off).
3. consecutiveShiftLimits: Max shifts/days in a row.
4. weeklyFrequencyLimits: Max frequency per week for a specific shift type.
5. crossDayDependencies: Night shift means off next morning.
6. conditionalRestrictions: If working for client X, cannot do Y shift.
7. crewSizeRestrictions: Min/max people on the job.
8. leadershipRestrictions: Ban/limit on acting as leader.
9. jobTypeRestrictions: Ban/preference for job types or clients.
10. vehicleRestrictions: Limits on vehicle driving.
11. interpersonalConflicts: Must not work with specific employee.

## 4. AVAILABLE SKILLS
Regular skills: Heavy Carry, Stair Carry, HHG, IT, Lead (2-8 ppl), Lead (9-15 ppl),
Lead (small deliveries), Supervisor (16-25 ppl), Truck Driver, Van Driver,
Installer (Basic), Installer (Standard), Installer (Advanced), Installer (Hanging),
Installer (New Furniture), Packer (Household), Packer (Commercial),
Whse 1 Helper, Whse 4 Helper, OMD Equip Repair

Certifications (use prefix "Certification (...)"):
Certification (WHMIS), Certification (Fall Arrest), Certification (CANA)

## 5. CLIENT REGISTRY (ONLY use these for lovedByCompanies / hatedByCompanies)
{_CLIENT_TABLE}

## 6. softConstraints SCHEMA
Output softConstraints matching this structure. Omit empty arrays/null fields:
{{
  "consecutiveShiftLimits": [{{"shiftType": "evening|morning|night|any", "maxConsecutive": int, "timeUnit": "shifts|days"}}],
  "dailyTimeRestrictions": {{"startTimeAfter": "HH:MM", "endTimeBefore": "HH:MM", "maxDailyHours": float, "appliesToDays": ["monday"]}},
  "recurringTimeOffPatterns": [{{"pattern": "every_other|every_second", "timeUnit": "week", "appliesToDays": ["saturday"], "startWeekUnknown": bool}}],
  "crossDayDependencies": [{{"ifShift": "evening", "thenCannotWork": "morning", "nextDayOffset": 1}}],
  "weeklyFrequencyLimits": [{{"shiftType": "night|double", "maxPerWeek": int}}],
  "conditionalRestrictions": [{{"trigger": {{"type": "job_assignment", "clientName": "...", "shiftType": "any", "dayOffset": 0}}, "consequence": {{"action": "cannot_assign", "toShiftType": "night", "onDayOffset": 0}}, "originalPhrase": "..."}}],
  "advanceNoticeRequired": [{{"shiftType": "weekend", "daysRequired": int, "ambiguous": bool}}],
  "crewSizeRestrictions": {{"minCrewSize": int, "maxCrewSize": int, "allowedSizes": null, "appliesToLeadershipOnly": bool}},
  "leadershipRestrictions": [{{"maxCrewSize": null, "allowedJobTypes": ["Residential"], "entityResolutionRequired": false}}],
  "jobTypeRestrictions": {{"whitelist": null, "blacklist": ["Large Office Moving"], "whitelistClients": ["CBE"], "blacklistClients": null, "entityResolutionRequired": false}},
  "vehicleRestrictions": [{{"vehicleType": "truck|van|any", "restrictionType": "no_day_and_night|no_double|cannot_drive"}}],
  "interpersonalConflicts": [{{"conflictEmployeeName": "...", "conflictType": "cannot_work_together|avoid_if_possible", "softConstraint": bool}}]
}}

## 7. CHAIN OF THOUGHT
1. Analyze the persona traits.
2. Set AM/PM boolean fields logically.
3. Choose skills/certifications matching seniority.
4. Write limitationInstructions triggering 2-3 constraints using "Must not" / "Try not to".
5. Fill softConstraints to match the limitationInstructions exactly.
6. Pick 0-3 lovedByCompanies and 0-2 hatedByCompanies from Section 5.
7. Validate: priority enum, certification prefix, names consistent.

## 8. OUTPUT FORMAT
Output ONLY valid JSON (no markdown). Schema:
{{
  "employee": {{
    "id": null,
    "name": "[realistic name]",
    "priority": "Regular|Part-Time|Extras",
    "rating": 1,
    "prefHrs": 40,
    "mondayAm": false, "mondayPm": true,
    "tuesdayAm": false, "tuesdayPm": true,
    "wednesdayAm": false, "wednesdayPm": true,
    "thursdayAm": false, "thursdayPm": true,
    "fridayAm": false, "fridayPm": true,
    "saturdayAm": false, "saturdayPm": false,
    "sundayAm": false, "sundayPm": false,
    "personalities": ["persona trait"],
    "additionalNotes": "realistic edge-case note",
    "preferredJobTypes": ["HHG", "WH"],
    "avoidedJobTypes": ["MOV"],
    "lovedByCompanies": [{{"clientId": 2, "clientName": "ATCO Blue Flame Kitchen"}}],
    "hatedByCompanies": []
  }},
  "limitation": {{
    "effectiveDate": "2026-05-01",
    "limitationInstructions": "natural language text with Must not / Try not to"
  }},
  "skills": ["Heavy Carry", "Certification (WHMIS)"],
  "softConstraints": {{ ... }}
}}
"""
