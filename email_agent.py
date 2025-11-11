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
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pos-agent@mvp.com")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

# ---------------- Utility: AI Email Draft ----------------
def generate_ai_email(context: str) -> dict:
    """
    Uses Groq LLM to generate email subject & body based on context.
    Returns: {"subject": str, "body": str}
    """
    system_prompt = """
    You are a helpful email writing assistant.
    Compose a short, polite, and professional email based on the provided context.
    Maintain a natural tone and output ONLY valid JSON:
    {
        "subject": "<subject>",
        "body": "<body>"
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

    try:
        ai_email = json.loads(completion.choices[0].message.content.strip())
        return ai_email
    except json.JSONDecodeError:
        return {
            "subject": "AI Draft Email",
            "body": completion.choices[0].message.content.strip(),
        }

# ---------------- Utility: Send Email via Brevo ----------------
def send_brevo_email(to_email: str, subject: str, body: str):
    """
    Sends an email using Brevo's transactional API.
    """
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "POS AI Agent", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()

# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "✅ AI Email Agent Running (Brevo)",
        "endpoints": ["/create_draft (POST)"]
    }), 200


@app.route("/create_draft", methods=["POST"])
def create_draft():
    """
    Create an AI-generated email draft and send it via Brevo.
    """
    try:
        data = request.get_json(force=True)
        recipient = data.get("to")
        context = data.get("context")

        if not recipient or not context:
            return jsonify({"error": "Missing 'to' or 'context'."}), 400

        ai_email = generate_ai_email(context)
        subject, body = ai_email["subject"], ai_email["body"]

        brevo_response = send_brevo_email(recipient, subject, body)

        return jsonify({
            "status": "✅ AI Draft Created & Sent via Brevo",
            "to": recipient,
            "subject": subject,
            "body_preview": body[:200],
            "brevo_response": brevo_response
        }), 200

    except Exception as e:
        print("❌ Error:", e)
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10003))
    app.run(host="0.0.0.0", port=port)
