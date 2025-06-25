# --- START OF FILE database.py ---

import json
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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