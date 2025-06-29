# --- START OF FILE database.py ---

import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __bind_key__ = 'airports' # Store users in the same DB as hubs
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def __repr__(self):
        return f'<User {self.username}>'

class Hub(db.Model):
    __bind_key__ = 'airports'
    id = db.Column(db.Integer, primary_key=True)
    iata = db.Column(db.String(4), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    tz = db.Column(db.String(50), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    runways_json = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    def as_dict(self):
        runways = []
        try:
            if self.runways_json:
                runways = json.loads(self.runways_json)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode runways_json for hub {self.iata}. Returning empty list for runways.")
            pass # runways is already initialized to []
        
        return {
            "iata": self.iata,
            "name": self.name,
            "city": self.city,
            "tz": self.tz,
            "lat": self.lat,
            "lon": self.lon,
            "runways": runways
        }

class HourlyWeather(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    iata = db.Column(db.String(4), index=True, nullable=False)
    start_time = db.Column(db.String(40), index=True, nullable=False)
    data_json = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(10), index=True, nullable=False)

    def as_dict(self):
        return {
            "iata": self.iata,
            "startTime": self.start_time,
            **json.loads(self.data_json)
        }

class HourlySnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    iata = db.Column(db.String(4), index=True, nullable=False)
    date = db.Column(db.String(10), index=True, nullable=False)
    hour = db.Column(db.Integer, index=True, nullable=False)
    snapshot_json = db.Column(db.Text, nullable=False)
    def as_dict(self):
        return {
            "iata": self.iata,
            "date": self.date,
            "hour": self.hour,
            **json.loads(self.snapshot_json)
        }

def init_db(app):
    with app.app_context():
        db.create_all()
# --- END OF FILE database.py ---
