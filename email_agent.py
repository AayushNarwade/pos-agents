from flask import Flask, request, jsonify
import os
import requests
from dotenv import load_dotenv
from groq import Groq
import json
import re
import traceback

# ---------------- Load Environment ----------------
load_dotenv()
app = Flask(__name__)

# ---------------- Configuration ----------------
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pos-agent@mvp.com")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

# ---------------- Utility: Clean AI JSON ----------------
def extract_json(text: str):
    """Extract JSON object from model text (handles markdown fences, codeblocks, etc)."""
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
    except Exception:
        pass
    return {"subject": "Follow-up Email", "body": text.strip()}


# ---------------- Utility: AI Email Draft ----------------
def generate_ai_email(context: str) -> dict:
    """
    Uses Groq LLM to generate a professional, human-like email.
    Returns: {"subject": str, "body": str}
    """
    system_prompt = """
    You are a professional email writing assistant.
    Craft a complete, well-structured email based on the given context.
    Follow these rules strictly:
    - Write in a clear, polite, business tone.
    - Start with a greeting (e.g., 'Hi <Name>,' or 'Hello Team,').
    - Include 2–3 short paragraphs.
    - End with a closing (e.g., 'Best regards,' or 'Thank you,').
    - Make the subject short and professional.
    - Do NOT return extra explanations or markdown.
    - Output ONLY valid JSON in this exact format:
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

    ai_text = completion.choices[0].message.content.strip()
    ai_email = extract_json(ai_text)
    return ai_email


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

    # Nicely formatted HTML email
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #222;">
        {body.replace('\n', '<br>')}
        <br><br>
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
        "status": "✅ Enhanced AI Email Agent Active",
        "endpoint": "/create_draft (POST)"
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
        subject = ai_email.get("subject", "AI Generated Email")
        body = ai_email.get("body", "Hello,\n\nThis is an AI-generated message.\n\nBest,\nPOS Agent")

        brevo_response = send_brevo_email(recipient, subject, body)

        return jsonify({
            "status": "✅ Email Draft Created & Sent",
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
    port = int(os.getenv("PORT", 10003))  # ✅ Dynamic for Render
    print(f"🚀 Email Agent running on port {port}")
    app.run(host="0.0.0.0", port=port)
