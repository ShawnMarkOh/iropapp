# --- START OF FILE services.py ---

import os
import re
import json
import requests
import pytz
from datetime import datetime, timedelta
from xml.etree import ElementTree
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from config import HUBS, INACTIVE_HUBS, LOG_FILE, FAA_OPS_PLAN_URL_CACHE, GROUND_STOPS_CACHE, GROUND_DELAYS_CACHE
from database import db, HourlyWeather, HourlySnapshot

NWS_GRID_CACHE = {}

def load_daily_log():
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            try:
                data = json.load(f)
                if data.get("date") == today_str:
                    return data
            except Exception:
                pass
    return {"date": today_str, "hubs": {}}

def save_daily_log(log_data):
    with open(LOG_FILE, "w") as f:
        json.dump(log_data, f)

def get_nws_grid(iata):
    if iata in NWS_GRID_CACHE:
        return NWS_GRID_CACHE[iata]
    
    all_hubs = HUBS + INACTIVE_HUBS
    for hub in all_hubs:
        if hub["iata"] == iata:
            lat, lon = hub.get("lat"), hub.get("lon")
            if lat and lon:
                resp = requests.get(f"https://api.weather.gov/points/{lat},{lon}", timeout=15)
                resp.raise_for_status()
                grid = resp.json()
                props = grid["properties"]
                result = {
                    "forecast": props["forecast"],
                    "forecastHourly": props["forecastHourly"],
                    "timezone": props["timeZone"],
                    "forecastZone": props.get("forecastZone")
                }
                NWS_GRID_CACHE[iata] = result
                return result
    return None

def fetch_weather_alerts(zone_url):
    if not zone_url:
        return []
    try:
        zone_id = zone_url.split('/')[-1]
        alerts_url = f"https://api.weather.gov/alerts/active/zone/{zone_id}"
        resp = requests.get(alerts_url, headers={"Accept": "application/geo+json"}, timeout=15)
        resp.raise_for_status()
        return resp.json().get("features", [])
    except requests.RequestException as e:
        print(f"Error fetching weather alerts for zone {zone_url}: {e}")
        return []

def get_latest_ops_plan_json():
    now = datetime.utcnow()
    cache = FAA_OPS_PLAN_URL_CACHE
    if cache.get("json") and cache.get("time") and (now - cache["time"]).total_seconds() < 600:
        return cache["json"]
    try:
        api_url = "https://nasstatus.faa.gov/api/operations-plan"
        resp = requests.get(api_url, timeout=10)
        if resp.ok:
            data = resp.json()
            FAA_OPS_PLAN_URL_CACHE.update({"json": data, "time": now})
            return data
    except Exception:
        pass
    FAA_OPS_PLAN_URL_CACHE.update({"json": None, "time": now})
    return None

def parse_faa_ops_plan_json(data, base_date=None):
    if not data or "terminalPlanned" not in data:
        return []

    plan_date = None
    if "link" in data:
        link = data["link"]
        # Try to find adv_date=MMDDYYYY
        match = re.search(r'adv_date=(\d{2})(\d{2})(\d{4})', link)
        if match:
            month, day, year = map(int, match.groups())
            plan_date = datetime(year, month, day).date()
        else:
            # Fallback to titleDate=MM/DD/YYYY
            match = re.search(r'titleDate=(\d{2})/(\d{2})/(\d{4})', link)
            if match:
                month, day, year = map(int, match.groups())
                plan_date = datetime(year, month, day).date()

    events = []
    for item in data["terminalPlanned"]:
        time_str = item.get("time", "")
        event_str = item.get("event", "")
        iatas = re.findall(r'\b([A-Z]{3})\b', event_str)
        for iata in iatas:
            m = re.match(r"(AFTER|UNTIL) (\d{4})", time_str)
            if not m:
                continue
            when_type, zulu_time = m.group(1), m.group(2)
            dt_utc = datetime.utcnow()
            event_hour = int(zulu_time[:2])
            event_min = int(zulu_time[2:])
            
            ref_date = plan_date or base_date or dt_utc.date()
            
            event_dt_utc = datetime(ref_date.year, ref_date.month, ref_date.day, event_hour, event_min, tzinfo=pytz.utc)

            # This logic is for rolling over to the next day. It should only apply if the plan is for today.
            if when_type == "AFTER" and ref_date == dt_utc.date() and dt_utc.hour >= event_hour:
                event_dt_utc += timedelta(days=1)

            events.append({
                "iata": iata,
                "when_type": when_type,
                "zulu_time": zulu_time,
                "desc": event_str,
                "when": time_str,
                "event_dt_utc": event_dt_utc.isoformat()
            })
    return events

def get_faa_events_by_day(dt):
    data = get_latest_ops_plan_json()
    if not data:
        return []
    return parse_faa_ops_plan_json(data, base_date=dt)

def get_events_for_hub_day(hub_iata, local_dt, tz_str):
    utc_dt = local_dt.astimezone(pytz.utc)
    events = get_faa_events_by_day(utc_dt.date())
    result = []
    after_events = []
    until_events = []

    tz = pytz.timezone(tz_str)
    viewing_date_local = local_dt.date()

    for e in events:
        if e["iata"] != hub_iata:
            continue
        
        event_dt_utc = datetime.fromisoformat(e['event_dt_utc'])
        dt_local = event_dt_utc.astimezone(tz)

        if e["when_type"] == "AFTER":
            # Event starts at dt_local and continues.
            # We are interested if it affects viewing_date_local.
            if dt_local.date() <= viewing_date_local:
                after_events.append({
                    "from_hour": dt_local.hour if dt_local.date() == viewing_date_local else -1,
                    "desc": e["desc"], "zulu_time": e["zulu_time"], "when": e["when"],
                    "when_type": e["when_type"], "local_time_iso": dt_local.isoformat(),
                })
        elif e["when_type"] == "UNTIL":
            # Event is active until dt_local.
            # We are interested if it affects viewing_date_local.
            if dt_local.date() >= viewing_date_local:
                until_events.append({
                    "to_hour": dt_local.hour if dt_local.date() == viewing_date_local else 24,
                    "desc": e["desc"], "zulu_time": e["zulu_time"], "when": e["when"],
                    "when_type": e["when_type"], "local_time_iso": dt_local.isoformat(),
                })
        else:
            # Specific time event (not currently parsed, but for future)
            if dt_local.date() == viewing_date_local:
                result.append({
                    "local_hour": dt_local.hour,
                    "local_minute": dt_local.minute,
                    "local_time_str": dt_local.strftime("%H:%M"),
                    "z_hour": event_dt_utc.hour,
                    "z_minute": event_dt_utc.minute,
                    "desc": e["desc"],
                    "zulu_time": e["zulu_time"],
                    "when": e["when"],
                    "when_type": e["when_type"],
                    "local_time_iso": dt_local.isoformat(),
                })

    for ae in after_events:
        for hr in range(ae["from_hour"] + 1, 24):
            result.append({
                "local_hour": hr, "local_minute": 0, "local_time_str": f"{hr:02d}:00",
                "z_hour": None, "z_minute": None, "desc": ae["desc"], "zulu_time": ae["zulu_time"],
                "when": ae["when"], "when_type": ae["when_type"], "local_time_iso": "",
            })
    for ue in until_events:
        for hr in range(0, ue["to_hour"] + 1):
            result.append({
                "local_hour": hr, "local_minute": 0, "local_time_str": f"{hr:02d}:00",
                "z_hour": None, "z_minute": None, "desc": ue["desc"], "zulu_time": ue["zulu_time"],
                "when": ue["when"], "when_type": ue["when_type"], "local_time_iso": "",
            })
    return result

def fetch_and_log_weather(iata):
    grid = get_nws_grid(iata)
    if not grid:
        return None
    try:
        resp_hourly = requests.get(grid["forecastHourly"], timeout=15)
        resp_hourly.raise_for_status()
        hourly = resp_hourly.json()
        hourly_periods = hourly.get("properties", {}).get("periods", [])

        resp_daily = requests.get(grid["forecast"], timeout=15)
        resp_daily.raise_for_status()
        daily = resp_daily.json()
        daily_periods = daily.get("properties", {}).get("periods", [])

        alerts = fetch_weather_alerts(grid.get("forecastZone"))

        now = datetime.now(pytz.timezone(grid["timezone"]))
        now_utc = datetime.now(pytz.utc)
        
        # Find the current hour's forecast period to save to the database.
        current_period = None
        if hourly_periods:
            for period in hourly_periods:
                # NWS times are ISO 8601 strings.
                start_time = datetime.fromisoformat(period["startTime"])
                end_time = datetime.fromisoformat(period["endTime"])
                if start_time <= now_utc < end_time:
                    current_period = period
                    break
        
        if current_period:
            key = current_period["startTime"]
            # Only save if it's a new hour and we haven't saved it before.
            exists = HourlyWeather.query.filter_by(iata=iata, start_time=key).first()
            if not exists:
                ymd = now.strftime("%Y-%m-%d")
                db.session.add(HourlyWeather(
                    iata=iata,
                    start_time=key,
                    data_json=json.dumps(current_period),
                    date=ymd
                ))
                db.session.commit()

        return {
            "hourly": hourly_periods,
            "daily": daily_periods,
            "timezone": grid["timezone"],
            "alerts": alerts
        }
    except requests.RequestException as e:
        print(f"Error fetching weather for {iata}: {e}")
        return None

def fetch_faa_ground_stops():
    url = "https://nasstatus.faa.gov/api/airport-status-information"
    output = {}
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        # Handle JSON response first
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            data = resp.json()
            for ap in data.get("AirportStatusList", []):
                iata = ap.get("IATA")
                for gs in ap.get("GroundStops", []):
                    if gs.get("EndTime"):
                        reason = gs.get("Reason", "Ground stop in effect")
                        end_time = gs.get("EndTime", "")
                        if iata:
                            output[iata] = {"reason": reason, "end_time": end_time}
            return output

        # Fallback to XML response (potentially wrapped in HTML)
        xml_string = resp.text
        if resp.text.strip().lower().startswith(("<html", "<!doctype html")):
            soup = BeautifulSoup(resp.text, 'html.parser')
            xml_div = soup.find('div', id='webkit-xml-viewer-source-xml')
            if xml_div and xml_div.contents:
                xml_string = str(xml_div.contents[0])
            else:
                xml_string = resp.text

        if "AIRPORT_STATUS_INFORMATION" in xml_string:
            root = ElementTree.fromstring(xml_string)
            for program in root.findall(".//Ground_Stop_List/Program"):
                iata = program.findtext("ARPT")
                reason = program.findtext("Reason") or "Ground stop in effect"
                end_time = program.findtext("End_Time") or ""
                if iata:
                    output[iata] = {"reason": reason, "end_time": end_time}
            return output

    except Exception as e:
        print(f"Error in fetch_faa_ground_stops: {e}")
        pass
    return output

def fetch_faa_ground_delays():
    url = "https://nasstatus.faa.gov/api/airport-status-information"
    output = {}
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        # Handle JSON response first
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            data = resp.json()
            for ap in data.get("AirportStatusList", []):
                iata = ap.get("IATA")
                for gd in ap.get("GroundDelays", []):
                    reason = gd.get("Reason", "Ground delay in effect")
                    avg_delay = gd.get("AvgDelay", "N/A")
                    if iata:
                        output[iata] = {"reason": reason, "avg_delay": avg_delay}
            return output

        # Fallback to XML response (potentially wrapped in HTML)
        xml_string = resp.text
        if resp.text.strip().lower().startswith(("<html", "<!doctype html")):
            soup = BeautifulSoup(resp.text, 'html.parser')
            xml_div = soup.find('div', id='webkit-xml-viewer-source-xml')
            if xml_div and xml_div.contents:
                xml_string = str(xml_div.contents[0])
            else:
                xml_string = resp.text

        if "AIRPORT_STATUS_INFORMATION" in xml_string:
            root = ElementTree.fromstring(xml_string)
            for gd in root.findall(".//Ground_Delay"):
                iata = gd.findtext("ARPT")
                reason = gd.findtext("Reason") or "Ground delay in effect"
                avg_delay = gd.findtext("Avg") or "N/A"
                if iata:
                    output[iata] = {"reason": reason, "avg_delay": avg_delay}
            return output

    except Exception as e:
        print(f"Error in fetch_faa_ground_delays: {e}")
        pass
    return output

def import_from_db_file(filepath):
    source_engine = create_engine(f'sqlite:///{filepath}')
    
    inspector = inspect(source_engine)
    
    imported_counts = {"hourly_weather": 0, "hourly_snapshot": 0}
    
    # Import HourlyWeather
    if inspector.has_table('hourly_weather'):
        with source_engine.connect() as connection:
            result = connection.execute("SELECT iata, start_time, data_json, date FROM hourly_weather")
            source_weather = result.fetchall()
            for row in source_weather:
                exists = HourlyWeather.query.filter_by(iata=row[0], start_time=row[1]).first()
                if not exists:
                    new_weather = HourlyWeather(
                        iata=row[0],
                        start_time=row[1],
                        data_json=row[2],
                        date=row[3]
                    )
                    db.session.add(new_weather)
                    imported_counts["hourly_weather"] += 1

    # Import HourlySnapshot
    if inspector.has_table('hourly_snapshot'):
        with source_engine.connect() as connection:
            result = connection.execute("SELECT iata, date, hour, snapshot_json FROM hourly_snapshot")
            source_snapshots = result.fetchall()
            for row in source_snapshots:
                exists = HourlySnapshot.query.filter_by(iata=row[0], date=row[1], hour=row[2]).first()
                if not exists:
                    new_snapshot = HourlySnapshot(
                        iata=row[0],
                        date=row[1],
                        hour=row[2],
                        snapshot_json=row[3]
                    )
                    db.session.add(new_snapshot)
                    imported_counts["hourly_snapshot"] += 1
    
    if imported_counts["hourly_weather"] > 0 or imported_counts["hourly_snapshot"] > 0:
        db.session.commit()
        
    return imported_counts
# --- END OF FILE services.py ---
