# --- START OF FILE services.py ---

import os
import re
import json
import requests
import pytz
from datetime import datetime, timedelta

from config import HUBS, LOG_FILE, FAA_OPS_PLAN_URL_CACHE
from database import db, HourlyWeather, HourlySnapshot

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

def get_latlon_for_hub(iata):
    lookup = {
        "CLT": (35.2140, -80.9431),
        "PHL": (39.8744, -75.2424),
        "DCA": (38.8521, -77.0377),
        "DAY": (39.9024, -84.2194),
        "DFW": (32.8998, -97.0403)
    }
    return lookup.get(iata, (None, None))

def get_nws_grid(iata):
    for hub in HUBS:
        if hub["iata"] == iata:
            lat, lon = get_latlon_for_hub(hub["iata"])
            if lat and lon:
                resp = requests.get(f"https://api.weather.gov/points/{lat},{lon}", timeout=15)
                resp.raise_for_status()
                grid = resp.json()
                props = grid["properties"]
                return {
                    "forecast": props["forecast"],
                    "forecastHourly": props["forecastHourly"],
                    "timezone": props["timeZone"]
                }
    return None

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
            ref_date = base_date or dt_utc.date()
            event_dt_utc = datetime(dt_utc.year, dt_utc.month, dt_utc.day, event_hour, event_min, tzinfo=pytz.utc)
            if when_type == "AFTER" and dt_utc.hour >= event_hour:
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
    for e in events:
        if e["iata"] != hub_iata:
            continue
        z_hour = int(e["zulu_time"][:2])
        z_min = int(e["zulu_time"][2:])
        dt_utc = datetime(utc_dt.year, utc_dt.month, utc_dt.day, z_hour, z_min, tzinfo=pytz.utc)
        dt_local = dt_utc.astimezone(pytz.timezone(tz_str))
        if e["when_type"] == "AFTER":
            if local_dt.hour >= dt_local.hour:
                dt_local = dt_local + timedelta(days=1)
        if e["when_type"] == "AFTER":
            after_events.append({
                "from_hour": dt_local.hour,
                "from_minute": dt_local.minute,
                "desc": e["desc"],
                "zulu_time": e["zulu_time"],
                "when": e["when"],
                "when_type": e["when_type"],
                "local_time_iso": dt_local.isoformat(),
            })
        elif e["when_type"] == "UNTIL":
            until_events.append({
                "to_hour": dt_local.hour,
                "to_minute": dt_local.minute,
                "desc": e["desc"],
                "zulu_time": e["zulu_time"],
                "when": e["when"],
                "when_type": e["when_type"],
                "local_time_iso": dt_local.isoformat(),
            })
        else:
            result.append({
                "local_hour": dt_local.hour,
                "local_minute": dt_local.minute,
                "local_time_str": dt_local.strftime("%H:%M"),
                "z_hour": z_hour,
                "z_minute": z_min,
                "desc": e["desc"],
                "zulu_time": e["zulu_time"],
                "when": e["when"],
                "when_type": e["when_type"],
                "local_time_iso": dt_local.isoformat(),
            })
    for ae in after_events:
        for hr in range(ae["from_hour"] + 1, 24):
            result.append({
                "local_hour": hr,
                "local_minute": 0,
                "local_time_str": f"{hr:02d}:00",
                "z_hour": None,
                "z_minute": None,
                "desc": ae["desc"],
                "zulu_time": ae["zulu_time"],
                "when": ae["when"],
                "when_type": ae["when_type"],
                "local_time_iso": "",
            })
    for ue in until_events:
        for hr in range(0, ue["to_hour"] + 1):
            result.append({
                "local_hour": hr,
                "local_minute": 0,
                "local_time_str": f"{hr:02d}:00",
                "z_hour": None,
                "z_minute": None,
                "desc": ue["desc"],
                "zulu_time": ue["zulu_time"],
                "when": ue["when"],
                "when_type": ue["when_type"],
                "local_time_iso": "",
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
        hourly_periods = hourly["properties"]["periods"]

        resp_daily = requests.get(grid["forecast"], timeout=15)
        resp_daily.raise_for_status()
        daily = resp_daily.json()
        daily_periods = daily["properties"]["periods"]

        now = datetime.now(pytz.timezone(grid["timezone"]))
        today_str = now.strftime("%Y-%m-%d")

        for period in hourly_periods:
            dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(pytz.timezone(grid["timezone"]))
            ymd = dt.strftime("%Y-%m-%d")
            key = period["startTime"]
            exists = HourlyWeather.query.filter_by(iata=iata, start_time=key).first()
            if not exists and ymd == today_str:
                db.session.add(HourlyWeather(
                    iata=iata,
                    start_time=key,
                    data_json=json.dumps(period),
                    date=ymd
                ))
        db.session.commit()

        return {
            "hourly": hourly_periods,
            "daily": daily_periods,
            "timezone": grid["timezone"]
        }
    except requests.RequestException as e:
        print(f"Error fetching weather for {iata}: {e}")
        return None
# --- END OF FILE services.py ---