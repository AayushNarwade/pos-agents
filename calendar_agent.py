from flask import Flask, request, jsonify
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
from googleapiclient.discovery import build
from google.oauth2 import service_account
from groq import Groq

# ----------------- Load ENV -----------------
load_dotenv()
app = Flask(__name__)

# ----------------- CONFIG -----------------
SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/etc/secrets/google_service_key.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IST = pytz.timezone("Asia/Kolkata")

# ----------------- AUTHENTICATION -----------------
service = None
try:
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )
    service = build("calendar", "v3", credentials=creds)
    print("✅ Google Calendar Agent authenticated successfully.")
except Exception as e:
    print("❌ Google Auth Error:", e)

client = Groq(api_key=GROQ_API_KEY)

# ----------------- HELPERS -----------------
def parse_message_with_ai(message: str):
    """
    Use Groq LLM to extract title, start_time, and end_time from plain English.
    Adds current date context to prevent year mismatch.
    """
    today_str = datetime.now(IST).strftime("%Y-%m-%d (%A)")
    system_prompt = f"""
    You are a precise meeting time parser.
    Today's date is {today_str}.
    Given a meeting request, extract:
    {{
        "title": "<title>",
        "start_time": "<ISO datetime format, Asia/Kolkata timezone>",
        "end_time": "<ISO datetime format, Asia/Kolkata timezone>"
    }}
    - The year must be 2025 (or current year).
    - Never output past dates.
    - If time only is given (like 'tomorrow 4 PM'), assume the next valid occurrence.
    - Always output valid JSON.
    - If end_time not given, assume 30 minutes after start_time.
    """

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        parsed = json.loads(completion.choices[0].message.content)

        # --- Safety correction: if AI date < now, push to future ---
        for key in ["start_time", "end_time"]:
            if key in parsed:
                dt = datetime.fromisoformat(parsed[key])
                if dt < datetime.now(IST):
                    dt = dt.replace(year=datetime.now(IST).year)
                    if dt < datetime.now(IST):
                        dt += timedelta(days=1)
                    parsed[key] = dt.isoformat()
        return parsed

    except Exception as e:
        print("⚠️ Groq parsing failed:", e)
        return None


# ----------------- ROUTES -----------------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "✅ Google Calendar Agent Running"}), 200


@app.route("/create_event", methods=["POST"])
def create_event():
    """Creates an event in Google Calendar."""
    if not service:
        return jsonify({"error": "Google Calendar service not initialized"}), 500

    try:
        data = request.get_json(force=True)
        print("📩 Incoming event data:", json.dumps(data, indent=2))

        # --- Step 1: If plain message provided, extract via Groq ---
        if "message" in data and not data.get("start_time"):
            ai_parsed = parse_message_with_ai(data["message"])
            if not ai_parsed:
                return jsonify({"error": "Could not parse event from message"}), 400
            data.update(ai_parsed)

        title = data.get("title", "Untitled Event")
        description = data.get("description", "")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if not start_time:
            return jsonify({"error": "start_time is required"}), 400

        # --- Step 2: Parse and localize ---
        start_dt = datetime.fromisoformat(start_time)
        if start_dt.tzinfo is None:
            start_dt = IST.localize(start_dt)

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
            if end_dt.tzinfo is None:
                end_dt = IST.localize(end_dt)
        else:
            end_dt = start_dt + timedelta(minutes=30)

        # --- Step 3: Ensure date is not in past ---
        now = datetime.now(IST)
        if start_dt < now:
            print("⚠️ Adjusting event to next valid day...")
            start_dt += timedelta(days=1)
            end_dt += timedelta(days=1)

        # --- Step 4: Create Event ---
        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        }

        event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event_body).execute()

        print(f"📆 Event Created: {event.get('htmlLink')}")
        return jsonify({
            "status": "✅ Event Created Successfully",
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
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port)
