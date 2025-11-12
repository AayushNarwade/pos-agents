from flask import Flask, request, jsonify
import os
import requests
from dotenv import load_dotenv
from groq import Groq
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


# ---------------- Utility: Extract Recipient ----------------
def extract_recipient(context: str):
    """
    Extracts an email address from the user's text.
    Example: "Send an email to john@example.com about project status"
    """
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", context)
    if match:
        return match.group(0)
    return None


# ---------------- Utility: AI Email Draft ----------------
def generate_ai_email(context: str) -> dict:
    """
    Uses Groq LLM to generate a well-written, professional email.
    No JSON format from the model — we handle formatting ourselves.
    """
    system_prompt = """
    You are a professional email writer.
    Write a short, polite, and clear business email based on the given context.
    The format should be:

    Subject: <a short, professional subject line>

    Body:
    <A professional email body written in a natural tone, with a greeting, 2–3 concise paragraphs, and a closing.>

    Do NOT use markdown, code fences, or JSON.
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

    # Extract subject & body manually
    subject_match = re.search(r"Subject:\s*(.*)", ai_text)
    subject = subject_match.group(1).strip() if subject_match else "Automated Email"

    # Extract everything after "Body:" or after the subject line
    body = re.split(r"Body:\s*", ai_text, maxsplit=1)
    body = body[1].strip() if len(body) > 1 else ai_text

    return {"subject": subject, "body": body}


# ---------------- Utility: Send Email via Brevo ----------------
def send_brevo_email(to_email: str, subject: str, body: str):
    """
    Sends the formatted email using Brevo's transactional API.
    """
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    # Clean HTML email layout
    html_body = f"""
    <html>
    <body style="font-family: 'Segoe UI', sans-serif; color: #333; line-height: 1.6;">
        {body.replace('\n', '<br>')}
        <br><br>
        <p style="margin-top: 20px;">
            Best regards,<br>
            <strong>POS AI Agent</strong><br>
            <span style="font-size: 12px; color: #888;">Automated Communication Assistant</span>
        </p>
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

    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "✅ Simplified AI Email Agent Active",
        "endpoint": "/create_draft (POST)"
    }), 200


@app.route("/create_draft", methods=["POST"])
def create_draft():
    """
    Generates and sends a professional email automatically.
    """
    try:
        data = request.get_json(force=True)
        user_input = data.get("context", "")
        explicit_recipient = data.get("to")

        # Extract recipient dynamically
        recipient = explicit_recipient or extract_recipient(user_input)
        if not recipient:
            return jsonify({"error": "No valid recipient found in the message."}), 400

        # Clean context for AI
        sanitized_context = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", user_input)

        # Generate AI-composed email
        ai_email = generate_ai_email(sanitized_context)
        subject = ai_email["subject"]
        body = ai_email["body"]

        # Send via Brevo
        brevo_response = send_brevo_email(recipient, subject, body)

        # Clean preview for API response
        preview = f"Subject: {subject}\n\n{body[:250]}..."

        return jsonify({
            "status": "✅ Email Draft Created & Sent",
            "to": recipient,
            "subject": subject,
            "body_preview": preview,
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
    port = int(os.getenv("PORT", 10003))  # ✅ Render dynamic port
    print(f"🚀 Email Agent running on port {port}")
    app.run(host="0.0.0.0", port=port)
