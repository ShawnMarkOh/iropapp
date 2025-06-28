# --- START OF FILE config.py ---

import os
from datetime import datetime

# --- Directory and File Paths ---
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "daily.log.json")

# --- Database Configuration ---
SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(DATA_DIR, "weatherlog.db")}'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# --- Airport Hubs Data ---
HUBS = [
    {
        "name": "Charlotte Douglas International Airport",
        "iata": "CLT",
        "city": "Charlotte, NC",
        "tz": "America/New_York",
        "runways": [
            {"label": "18L/36R", "heading": 180, "len": 10000},
            {"label": "18C/36C", "heading": 180, "len": 10000},
            {"label": "18R/36L", "heading": 180, "len": 9000},
            {"label": "5/23",    "heading": 50,  "len": 7502},
        ]
    },
    {
        "name": "Philadelphia International Airport",
        "iata": "PHL",
        "city": "Philadelphia, PA",
        "tz": "America/New_York",
        "runways": [
            {"label": "9L/27R",  "heading": 90,  "len": 10000},
            {"label": "9R/27L",  "heading": 90,  "len": 9500},
            {"label": "17/35",   "heading": 170, "len": 6500},
        ]
    },
    {
        "name": "Ronald Reagan Washington National Airport",
        "iata": "DCA",
        "city": "Washington, DC",
        "tz": "America/New_York",
        "runways": [
            {"label": "1/19",    "heading": 10,  "len": 7169},
            {"label": "15/33",   "heading": 150, "len": 5204},
        ]
    },
    {
        "name": "Dayton International Airport",
        "iata": "DAY",
        "city": "Dayton, OH",
        "tz": "America/New_York",
        "runways": [
            {"label": "6L/24R",  "heading": 60,  "len": 10500},
            {"label": "18/36",   "heading": 180, "len": 7500},
            {"label": "6R/24L",  "heading": 60,  "len": 7100},
        ]
    },
    {
        "name": "Dallas/Fort Worth International Airport",
        "iata": "DFW",
        "city": "Dallas-Fort Worth, TX",
        "tz": "America/Chicago",
        "runways": [
            {"label": "13L/31R", "heading": 130, "len": 9000},
            {"label": "13R/31L", "heading": 130, "len": 9200},
            {"label": "17L/35R", "heading": 170, "len": 8500},
            {"label": "17C/35C", "heading": 170, "len": 13400},
            {"label": "17R/35L", "heading": 170, "len": 13400},
            {"label": "18L/36R", "heading": 180, "len": 13300},
            {"label": "18R/36L", "heading": 180, "len": 13400},
        ]
    },
    {
        "name": "O'Hare International Airport",
        "iata": "ORD",
        "city": "Chicago, IL",
        "tz": "America/Chicago",
        "runways": [
            {"label": "10L/28R", "heading": 100, "len": 13000},
            {"label": "9C/27C", "heading": 90, "len": 11260},
            {"label": "9L/27R", "heading": 90, "len": 11245},
            {"label": "10C/28C", "heading": 100, "len": 10801},
        ]
    }
]

INACTIVE_HUBS = []

# --- Caching ---
FAA_EVENTS_CACHE = {}
FAA_EVENTS_CACHE_TIME = {}
FAA_OPS_PLAN_URL_CACHE = {"json": None, "time": None}
GROUND_STOPS_CACHE = {"json": None, "time": None}
GROUND_DELAYS_CACHE = {"json": None, "time": None}
# --- END OF FILE config.py ---
