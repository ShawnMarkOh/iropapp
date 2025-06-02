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
        "lat": 35.214,
        "lon": -80.943,
        "tz": "America/New_York",
        "runways": [
            {"label": "18L/36R", "heading": 180, "len": 10000},
            {"label": "18C/36C", "heading": 180, "len": 10000},
            {"label": "18R/36L", "heading": 180, "len": 9000},
            {"label": "05/23", "heading": 54, "len": 7000},
        ]
    },
    {
        "name": "Philadelphia International Airport",
        "iata": "PHL",
        "city": "Philadelphia, PA",
        "lat": 39.8744,
        "lon": -75.2424,
        "tz": "America/New_York",
        "runways": [
            {"label": "09L/27R", "heading": 90, "len": 10006},
            {"label": "09R/27L", "heading": 90, "len": 9500},
            {"label": "17/35", "heading": 170, "len": 9500},
        ]
    },
    {
        "name": "Ronald Reagan Washington National Airport",
        "iata": "DCA",
        "city": "Washington, DC",
        "lat": 38.8521,
        "lon": -77.0377,
        "tz": "America/New_York",
        "runways": [
            {"label": "01/19", "heading": 10, "len": 6900},
            {"label": "15/33", "heading": 150, "len": 5200},
            {"label": "04/22", "heading": 40, "len": 5000},
        ]
    },
    {
        "name": "Dayton International Airport",
        "iata": "DAY",
        "city": "Dayton, OH",
        "lat": 39.9024,
        "lon": -84.2194,
        "tz": "America/New_York",
        "runways": [
            {"label": "06L/24R", "heading": 60, "len": 10500},
            {"label": "18/36", "heading": 180, "len": 7100},
        ]
    },
    {
        "name": "Dallas/Fort Worth International Airport",
        "iata": "DFW",
        "city": "Dallas-Fort Worth, TX",
        "lat": 32.8998,
        "lon": -97.0403,
        "tz": "America/Chicago",
        "runways": [
            {"label": "17C/35C", "heading": 170, "len": 13400},
            {"label": "18L/36R", "heading": 180, "len": 13400},
            {"label": "17R/35L", "heading": 170, "len": 13300},
            {"label": "17L/35R", "heading": 170, "len": 8500},
            {"label": "13R/31L", "heading": 130, "len": 9200},
            {"label": "13L/31R", "heading": 130, "len": 8200}
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
