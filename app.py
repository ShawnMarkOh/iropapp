# --- START OF FILE app.py ---

import os
import threading
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

import config
from database import db, init_db
from routes import init_routes
from tasks import init_tasks

# --- App Initialization ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS

# --- Extensions Initialization ---
CORS(app)
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Database and Routes Setup ---
# Create database tables if they don't exist
init_db(app)

# Register all the routes from routes.py
init_routes(app)

# --- Background Tasks ---
# Start background threads for data fetching
init_tasks(app, socketio)

# --- Main Execution ---
if __name__ == "__main__":
    socketio.run(app, debug=True)
# --- END OF FILE app.py ---