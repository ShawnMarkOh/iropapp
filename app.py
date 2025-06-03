import os
import requests
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
from xml.etree import ElementTree as ET
from datetime import datetime, timedelta
from pytz import timezone

app = Flask(__name__)
CORS(app)

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
            {"label": "17C/35C", "heading": 170, "len": 13400},
            {"label": "17L/35R", "heading": 170, "len": 8500},
            {"label": "17R/35L", "heading": 170, "len": 13400},
            {"label": "18L/36R", "heading": 180, "len": 13300},
            {"label": "18R/36L", "heading": 180, "len": 13400},
        ]
    }
]


@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/hubs')
def get_hubs():
    return jsonify(HUBS)

@app.route('/api/weather/<iata>')
def get_weather(iata):
    # Find hub
    hub = next((h for h in HUBS if h['iata'].upper() == iata.upper()), None)
    if not hub:
        return jsonify({'error': 'Unknown hub'}), 404

    # Get NWS gridpoints URL
    try:
        pt_url = f"https://api.weather.gov/points/{hub['lat']},{hub['lon']}"
        r = requests.get(pt_url, timeout=10)
        r.raise_for_status()
        pt_data = r.json()
        forecast_url = pt_data["properties"]["forecast"]
        hourly_url = pt_data["properties"]["forecastHourly"]
    except Exception as e:
        return jsonify({'error': 'NWS point lookup failed', 'details': str(e)}), 502

    # Get forecasts
    try:
        daily_r = requests.get(forecast_url, timeout=10)
        daily_r.raise_for_status()
        hourly_r = requests.get(hourly_url, timeout=10)
        hourly_r.raise_for_status()
        daily = daily_r.json()
        hourly = hourly_r.json()
        return jsonify({
            "daily": daily["properties"]["periods"],
            "hourly": hourly["properties"]["periods"],
        })
    except Exception as e:
        return jsonify({'error': 'NWS forecast failed', 'details': str(e)}), 502

@app.route('/api/groundstops')
def groundstops():
    url = "https://nasstatus.faa.gov/api/airport-status-information"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        tree = ET.fromstring(r.text)
        stops = {}
        for airport in tree.findall('.//airport'):
            iata_elem = airport.find('iata')
            if iata_elem is None:
                continue
            iata = iata_elem.text.strip().upper()
            gs = airport.find('groundstop')
            if gs is not None:
                type_elem = gs.find('type')
                status_elem = gs.find('status')
                if status_elem is not None and status_elem.text and status_elem.text.lower() == 'active':
                    reason_elem = gs.find('reason')
                    reason = reason_elem.text if reason_elem is not None else 'Ground Stop'
                    stops[iata] = reason
        return jsonify(stops)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch FAA ground stops', 'details': str(e)}), 502

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

if __name__ == '__main__':
    app.run(debug=True)
