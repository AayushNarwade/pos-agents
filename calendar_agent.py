from flask import Flask, request, jsonify
import os, json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
from googleapiclient.discovery import build
from google.oauth2 import service_account
from groq import Groq

load_dotenv()
app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/etc/secrets/google_service_key.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IST = pytz.timezone("Asia/Kolkata")

service = None
try:
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds)
    print("✅ Google Calendar Agent authenticated successfully.")
except Exception as e:
    print("❌ Google Auth Error:", e)

client = Groq(api_key=GROQ_API_KEY)

def parse_message_with_ai(message):
    today_str = datetime.now(IST).strftime("%Y-%m-%d (%A)")
    system_prompt = f"""
    You are a precise time parser. Today is {today_str}.
    Output JSON with "title", "start_time", "end_time" in ISO 8601 (Asia/Kolkata).
    Assume current year if missing. Never pick past dates.
    """
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "✅ Google Calendar Agent Running"}), 200

@app.route("/create_event", methods=["POST"])
def create_event():
    try:
        data = request.get_json(force=True)
        if "message" in data and not data.get("start_time"):
            ai_parsed = parse_message_with_ai(data["message"])
            data.update(ai_parsed)

        start_time = data.get("start_time")
        if not start_time:
            return jsonify({"error": "start_time is required"}), 400

        title = data.get("title", "Untitled Event")
        description = data.get("description", "")
        end_time = data.get("end_time")

        start_dt = datetime.fromisoformat(start_time)
        if start_dt.tzinfo is None:
            start_dt = IST.localize(start_dt)
        if end_time:
            end_dt = datetime.fromisoformat(end_time)
            if end_dt.tzinfo is None:
                end_dt = IST.localize(end_dt)
        else:
            end_dt = start_dt + timedelta(minutes=30)

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        }

        created_event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        calendar_link = created_event.get("htmlLink")

        return jsonify({
            "status": "✅ Event Created Successfully",
            "event_title": title,
            "calendar_link": calendar_link,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }), 200
    except Exception as e:
        print("❌ Error creating event:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10002))
    print(f"🚀 Calendar Agent running on port {port}")
    app.run(host="0.0.0.0", port=port)
