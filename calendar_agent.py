from flask import Flask, request, jsonify
import os, json, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq
import pytz

# ---------------- Setup ----------------
app = Flask(__name__)
load_dotenv()
IST = pytz.timezone("Asia/Kolkata")

# ---------------- ENV ----------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are the AI Calendar Agent of the Present Operating System.
Convert user messages into structured event details in this JSON format:
{
  "title": "<short descriptive title>",
  "description": "<what the event is about>",
  "start_time": "<ISO 8601 datetime in Asia/Kolkata>",
  "end_time": "<ISO 8601 datetime in Asia/Kolkata>"
}
If duration is missing, default to 1 hour.
If no date is given, assume today.
"""

def clean_json_output(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return text


def create_public_calendar_event(event_data):
    """Create an event directly on a public Google Calendar using API key."""
    url = f"https://www.googleapis.com/calendar/v3/calendars/{GOOGLE_CALENDAR_ID}/events?key={GOOGLE_API_KEY}"

    payload = {
        "summary": event_data["title"],
        "description": event_data.get("description", ""),
        "start": {
            "dateTime": event_data["start_time"],
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": event_data["end_time"],
            "timeZone": "Asia/Kolkata"
        }
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=10)

    if resp.status_code in [200, 201]:
        return resp.json()
    else:
        print("❌ Google Calendar Error:", resp.text)
        return {"error": resp.text}


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "✅ AI Calendar Agent (Public Calendar Mode) Running"}), 200


@app.route("/create_event", methods=["POST"])
def create_event():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Missing message"}), 400

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
            max_tokens=400,
        )

        raw = completion.choices[0].message.content.strip()
        event_data = json.loads(clean_json_output(raw))

        # Default duration = +1 hour
        if not event_data.get("end_time"):
            start = datetime.fromisoformat(event_data["start_time"])
            event_data["end_time"] = (start + timedelta(hours=1)).isoformat()

        result = create_public_calendar_event(event_data)

        if "error" in result:
            return jsonify({"status": "❌ Failed to create event", "details": result["error"]}), 500

        return jsonify({
            "status": "✅ Event Created in Public Calendar",
            "event_summary": event_data["title"],
            "start_time": event_data["start_time"],
            "end_time": event_data["end_time"],
            "event_link": result.get("htmlLink", "No link returned")
        }), 200

    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10002))
    print(f"🚀 AI Calendar Agent (Public Auto Save Mode) running on port {port}")
    app.run(host="0.0.0.0", port=port)
