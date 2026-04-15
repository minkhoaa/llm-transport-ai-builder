"""Static registry of known scheduling clients."""
from typing import List


CLIENTS: List[dict] = [
    {"clientId": 1,  "clientName": "Alberta Health Services"},
    {"clientId": 2,  "clientName": "ATCO Blue Flame Kitchen"},
    {"clientId": 3,  "clientName": "Calgary Board of Education"},
    {"clientId": 4,  "clientName": "Calgary Catholic School District"},
    {"clientId": 5,  "clientName": "Canadian Natural Resources Ltd. (CNRL)"},
    {"clientId": 6,  "clientName": "CDI Spaces"},
    {"clientId": 7,  "clientName": "Cenovus Energy Inc."},
    {"clientId": 8,  "clientName": "Chronos Group"},
    {"clientId": 9,  "clientName": "CNOOC Petroleum North America ULC"},
    {"clientId": 10, "clientName": "Henry Schein"},
    {"clientId": 11, "clientName": "Koch Logistics"},
    {"clientId": 12, "clientName": "NuQuest Integrated Systems"},
    {"clientId": 13, "clientName": "Obsidian Energy Ltd."},
    {"clientId": 14, "clientName": "Ovintiv Canada ULC"},
    {"clientId": 15, "clientName": "Paramount Resources Ltd."},
    {"clientId": 16, "clientName": "Patterson Dental"},
    {"clientId": 17, "clientName": "PCL Constructors Westcoast Inc."},
    {"clientId": 18, "clientName": "Petronas Energy Canada Ltd."},
    {"clientId": 19, "clientName": "Platform Calgary"},
    {"clientId": 20, "clientName": "South Bow Infrastructure Holdings Ltd."},
    {"clientId": 21, "clientName": "Strathcona Resources"},
    {"clientId": 22, "clientName": "University of Calgary"},
    {"clientId": 24, "clientName": "Enterprise Logistics Group"},
]

CLIENT_IDS = {c["clientId"] for c in CLIENTS}
CLIENT_NAMES = {c["clientName"] for c in CLIENTS}
