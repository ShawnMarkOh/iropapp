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
        "lat": 35.2140,
        "lon": -80.9431,
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
        "lat": 39.8744,
        "lon": -75.2424,
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
        "lat": 38.8521,
        "lon": -77.0377,
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
        "lat": 39.9024,
        "lon": -84.2194,
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
        "lat": 32.8998,
        "lon": -97.0403,
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
]

INACTIVE_HUBS = [
    {
        "name": "O'Hare International Airport",
        "iata": "ORD",
        "city": "Chicago, IL",
        "tz": "America/Chicago",
        "lat": 41.9742,
        "lon": -87.9073,
        "runways": [
            {"label": "10L/28R", "heading": 100, "len": 13000},
            {"label": "9C/27C",  "heading": 90,  "len": 11260},
            {"label": "9L/27R",  "heading": 90,  "len": 11245},
            {"label": "10C/28C", "heading": 100, "len": 10801},
        ]
    },
    {
        "name": "Greenville-Spartanburg International Airport",
        "iata": "GSP",
        "city": "Greenville, SC",
        "tz": "America/New_York",
        "lat": 34.8956,
        "lon": -82.2189,
        "runways": [
            {"label": "4/22", "heading": 40, "len": 11001}
        ]
    },
    {
        "name": "Akron-Canton Airport",
        "iata": "CAK",
        "city": "Akron, OH",
        "tz": "America/New_York",
        "lat": 40.9162,
        "lon": -81.4422,
        "runways": [
            {"label": "1/19", "heading": 10, "len": 7601},
            {"label": "5/23", "heading": 50, "len": 8204}
        ]
    },
    {
        "name": "McGhee Tyson Airport",
        "iata": "TYS",
        "city": "Knoxville, TN",
        "tz": "America/New_York",
        "lat": 35.8122,
        "lon": -83.9941,
        "runways": [
            {"label": "5L/23R", "heading": 50, "len": 9003},
            {"label": "5R/23L", "heading": 50, "len": 9000}
        ]
    },
    {
        "name": "Hartsfield-Jackson Atlanta International Airport",
        "iata": "ATL",
        "city": "Atlanta, GA",
        "tz": "America/New_York",
        "lat": 33.6407,
        "lon": -84.4277,
        "runways": [
            {"label": "8L/26R", "heading": 90, "len": 9000},
            {"label": "8R/26L", "heading": 90, "len": 9999},
            {"label": "9L/27R", "heading": 90, "len": 12390},
            {"label": "9R/27L", "heading": 90, "len": 9000},
            {"label": "10/28",  "heading": 90, "len": 9000}
        ]
    },
    {
        "name": "Pensacola International Airport",
        "iata": "PNS",
        "city": "Pensacola, FL",
        "tz": "America/Chicago",
        "lat": 30.4735,
        "lon": -87.1866,
        "runways": [
            {"label": "17/35", "heading": 170, "len": 7004},
            {"label": "8/26",  "heading": 80,  "len": 7000}
        ]
    },
    {
        "name": "Miami International Airport",
        "iata": "MIA",
        "city": "Miami, FL",
        "tz": "America/New_York",
        "lat": 25.7959,
        "lon": -80.2871,
        "runways": [
            {"label": "8L/26R", "heading": 90, "len": 8600},
            {"label": "9/27", "heading": 90, "len": 13016},
            {"label": "12/30", "heading": 120, "len": 9355}
        ]
    },
    {
        "name": "Phoenix Sky Harbor International Airport",
        "iata": "PHX",
        "city": "Phoenix, AZ",
        "tz": "America/Phoenix",
        "lat": 33.4342,
        "lon": -112.0116,
        "runways": [
            {"label": "8/26", "heading": 80, "len": 11489},
            {"label": "7L/25R", "heading": 80, "len": 10300},
            {"label": "7R/25L", "heading": 80, "len": 7800}
        ]
    },
    {
        "name": "Harrisburg International Airport",
        "iata": "MDT",
        "city": "Middletown, PA",
        "tz": "America/New_York",
        "lat": 40.1935,
        "lon": -76.7634,
        "runways": [
            {"label": "13/31", "heading": 130, "len": 10001}
        ]
    }
]

# --- Caching ---
FAA_EVENTS_CACHE = {}
FAA_EVENTS_CACHE_TIME = {}
FAA_OPS_PLAN_URL_CACHE = {"json": None, "time": None}
GROUND_STOPS_CACHE = {"json": None, "time": None}
GROUND_DELAYS_CACHE = {"json": None, "time": None}
# --- END OF FILE config.py ---
