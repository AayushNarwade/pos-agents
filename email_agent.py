from flask import Flask, request, jsonify
import os
import requests
from dotenv import load_dotenv
from groq import Groq
import json
import traceback

# ---------------- Load Environment ----------------
load_dotenv()

app = Flask(__name__)

# ---------------- Configuration ----------------
MAILTRAP_TOKEN = os.getenv("MAILTRAP_TOKEN")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pos-agent@mvp.com")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)

# ---------------- Utility Functions ----------------
def generate_ai_email(context: str) -> dict:
    """
    Uses Groq LLM to generate email subject and body based on context.
    Returns a dict with keys 'subject' and 'body'.
    """
    system_prompt = """
    You are a professional email writing assistant.
    Compose a short, polite, and contextually appropriate email based on the provided context.
    Maintain a natural, human-like tone (friendly, but not too casual).
    Output ONLY valid JSON with this format:
    {
        "subject": "<subject line>",
        "body": "<email body>"
    }
    """

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
        temperature=0.6,
        max_tokens=400,
    )

    raw_response = completion.choices[0].message.content.strip()

    try:
        ai_email = json.loads(raw_response)
        subject = ai_email.get("subject", "No Subject")
        body = ai_email.get("body", "")
    except json.JSONDecodeError:
        subject = "AI Draft Email"
        body = raw_response

    return {"subject": subject, "body": body}


def send_mailtrap_email(to_email: str, subject: str, body: str):
    """
    Sends the generated email draft to Mailtrap Sandbox using REST API v2 (HTTPS).
    """
    MAILTRAP_API_URL = "https://send.api.mailtrap.io/api/send"

    headers = {
        "Authorization": f"Bearer {MAILTRAP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "from": {"email": SENDER_EMAIL, "name": "POS AI Agent"},
        "to": [{"email": to_email}],
        "subject": subject,
        "text": body,
        "category": "AI Draft Email"
    }

    try:
        response = requests.post(MAILTRAP_API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        print(f"📧 Email successfully sent to Mailtrap API for {to_email}")
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print("❌ Mailtrap API error:", response.text)
        raise http_err
    except Exception as e:
        print("❌ Connection error:", e)
        traceback.print_exc()
        raise e


# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "✅ AI Email Agent Running (Render-ready, HTTPS-based)",
        "endpoints": ["/create_draft (POST)"]
    }), 200


@app.route("/create_draft", methods=["POST"])
def create_draft():
    """
    Create AI-generated email draft and send it to Mailtrap API.
    Expected JSON body:
    {
        "to": "someone@example.com",
        "context": "Thank John for the project update and confirm the next meeting."
    }
    """
    try:
        data = request.get_json(force=True)
        recipient = data.get("to")
        context = data.get("context")

        if not recipient or not context:
            return jsonify({"error": "Missing fields. Required: 'to' and 'context'."}), 400

        # 1️⃣ Generate draft using Groq AI
        ai_email = generate_ai_email(context)
        subject = ai_email["subject"]
        body = ai_email["body"]

        # 2️⃣ Send draft to Mailtrap via REST API
        api_response = send_mailtrap_email(recipient, subject, body)

        # 3️⃣ Return metadata response
        return jsonify({
            "status": "✅ AI Draft Created & Sent to Mailtrap (via HTTPS)",
            "to": recipient,
            "subject": subject,
            "body_preview": (body[:200] + "...") if len(body) > 200 else body,
            "preview_link": "https://mailtrap.io/inboxes",
            "mailtrap_response": api_response
        }), 200

    except Exception as e:
        print("❌ Error:", e)
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


# ---------------- Entry Point ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10003))  # Render injects PORT dynamically
    app.run(host="0.0.0.0", port=port)
