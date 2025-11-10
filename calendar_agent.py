from flask import Flask, request, jsonify
import os
import json
import tempfile
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
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
PORT = int(os.getenv("PORT", 10002))
IST = pytz.timezone("Asia/Kolkata")

# ----------------- AUTH -----------------

service = None
try:
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    if creds_json:
        import json
        creds_info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    elif GOOGLE_CREDENTIALS_PATH and os.path.exists(GOOGLE_CREDENTIALS_PATH):
        creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)
    else:
        raise Exception("No Google credentials found (JSON or file).")

    service = build("calendar", "v3", credentials=creds)
    print("✅ Google Calendar Agent authenticated successfully.")
except Exception as e:
    print("❌ Google Auth Error:", e)
    service = None


# ----------------- ROUTES -----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Calendar Agent Running ✅"})


@app.route("/create_event", methods=["POST"])
def create_event():
    if not service:
        return jsonify({"error": "Google Calendar service not initialized"}), 500

    try:
        data = request.get_json()

        title = data.get("title", "Untitled Event")
        description = data.get("description", "")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if not start_time:
            return jsonify({"error": "start_time is required"}), 400

        # Ensure ISO formatting
        start = datetime.fromisoformat(start_time)
        if not end_time:
            end_time = (start + timedelta(minutes=30)).isoformat()

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
    port = int(os.getenv("PORT", 10002))  # dynamically use Render’s port
    app.run(host="0.0.0.0", port=port)

