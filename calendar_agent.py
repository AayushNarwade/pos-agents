from flask import Flask, request, jsonify
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ----------------- Load ENV -----------------
load_dotenv()

app = Flask(__name__)

# ----------------- CONFIG -----------------
SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/etc/secrets/google_service_key.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
IST = pytz.timezone("Asia/Kolkata")

# ----------------- AUTH -----------------
service = None
try:
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(f"Credentials file not found at {GOOGLE_CREDENTIALS_PATH}")

    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )
    service = build("calendar", "v3", credentials=creds)
    print("✅ Google Calendar Agent authenticated successfully.")
except Exception as e:
    print("❌ Google Auth Error:", e)
    service = None


# ----------------- ROUTES -----------------
@app.route("/", methods=["GET"])
def home():
    """Health check route."""
    return jsonify({"status": "Calendar Agent Running ✅"}), 200


@app.route("/create_event", methods=["POST"])
def create_event():
    """Creates a new event in Google Calendar."""
    if not service:
        return jsonify({"error": "Google Calendar service not initialized"}), 500

    try:
        data = request.get_json(force=True)

        title = data.get("title", "Untitled Event")
        description = data.get("description", "")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        # Validate inputs
        if not start_time:
            return jsonify({"error": "start_time is required"}), 400

        # Convert to datetime and set default duration
        start = datetime.fromisoformat(start_time)
        if not end_time:
            end = start + timedelta(minutes=30)
            end_time = end.isoformat()

        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
        }

        event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event_body).execute()
        print(f"📆 Event Created: {event.get('htmlLink')}")

        return jsonify({
            "status": "Event Created ✅",
            "event_title": event.get("summary"),
            "start": event.get("start", {}).get("dateTime"),
            "end": event.get("end", {}).get("dateTime"),
            "html_link": event.get("htmlLink"),
        }), 200

    except Exception as e:
        print("❌ Error creating calendar event:", e)
        return jsonify({"error": str(e)}), 500


# ----------------- MAIN -----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10002))  # dynamically adapt to Render port
    app.run(host="0.0.0.0", port=port)
