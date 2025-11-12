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
    Uses Groq LLM to generate a professional, well-structured email.
    Returns: {"subject": str, "body": str}
    """
    system_prompt = """
    You are a professional corporate email assistant.
    Write clear, concise, and contextually appropriate business emails.
    Follow these strict guidelines:

    - Use a polite and confident tone.
    - Include a proper greeting and closing.
    - Make sure the subject is short, descriptive, and relevant.
    - The email body should have 2–4 short paragraphs (60–120 words total).
    - Always thank the recipient or acknowledge their role.
    - Avoid robotic phrasing like “Dear Marketing Team,” if not needed; adapt based on context.
    - Never add signatures; the sender name will be added automatically by the system.

    Return ONLY valid JSON in this exact format:
    {
        "subject": "<email subject>",
        "body": "<email body>"
    }
    """

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
        temperature=0.65,
        max_tokens=500,
    )

    # --- Parse AI response safely ---
    try:
        ai_response = completion.choices[0].message.content.strip()
        ai_email = json.loads(ai_response)
        return ai_email
    except Exception:
        # fallback if model returns raw text
        return {
            "subject": "Follow-up on Recent Task",
            "body": ai_response,
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

    # Create a formatted HTML email for professional appearance
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <p>{body.replace('\n', '<br>')}</p>
        <br>
        <p>Best regards,<br><strong>POS AI Agent</strong></p>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": "POS AI Agent", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": body,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()

# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "✅ AI Email Agent Running (Enhanced)",
        "endpoints": ["/create_draft (POST)"]
    }), 200


@app.route("/create_draft", methods=["POST"])
def create_draft():
    """
    Create an AI-generated professional email and send it via Brevo.
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
            "status": "✅ Professional Email Draft Created & Sent",
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


# ---------------- Main ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10003))  # ✅ Dynamic port for Render
    print(f"🚀 Email Agent running on port {port}")
    app.run(host="0.0.0.0", port=port)
