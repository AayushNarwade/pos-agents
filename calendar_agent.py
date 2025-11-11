from flask import Flask, request, jsonify
import os, json
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from groq import Groq
import requests

load_dotenv()
app = Flask(__name__)
IST = pytz.timezone("Asia/Kolkata")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_CALENDAR_API_KEY = os.getenv("GOOGLE_CALENDAR_API_KEY")  # if using direct API
GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are the Calendar Agent in the Present Operating System (POS).
Your job is to extract structured event details from natural language.
Return only valid JSON with keys: title, start_time, end_time, description.
Infer missing information when possible.
"""

def clean_json_output(text):
    text = text.strip()
    if text.startswith("```"): text = text.replace("```json", "").replace("```", "").strip()
    return text

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "✅ AI Calendar Agent Running"}), 200

@app.route("/create_event", methods=["POST"])
def create_event():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "")

        completion = GROQ_CLIENT.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
            max_tokens=400,
        )

        raw = completion.choices[0].message.content.strip()
        cleaned = clean_json_output(raw)
        event_data = json.loads(cleaned)

        # (Optional) Use Google Calendar API to create the event here
        event_link = f"https://calendar.google.com/event?action=TEMPLATE&text={event_data['title']}"

        response = {
            "calendar_link": event_link,
            "event_summary": event_data["title"],
            "start_time": event_data.get("start_time"),
            "end_time": event_data.get("end_time"),
            "description": event_data.get("description"),
        }

        print("📅 Created Event:", response)
        return jsonify(response), 200

    except Exception as e:
        print("❌ Calendar Agent Error:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10002))
    print(f"🚀 AI Calendar Agent running locally on port {port}")
    app.run(host="0.0.0.0", port=port)
