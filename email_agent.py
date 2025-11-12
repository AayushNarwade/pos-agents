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


# ---------------- Utility: Safe JSON Parser ----------------
def safe_parse_json(raw_text: str):
    """
    Ensures the model output is parsed as valid JSON, even if double-encoded or wrapped in markdown/code fences.
    """
    if not raw_text:
        return {}

    # Clean up markdown or code fences
    cleaned = re.sub(r"^```(?:json)?", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```$", "", cleaned.strip())

    # Extract JSON-like content
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return {"body": cleaned}

    json_candidate = match.group(0)

    # Try decoding multiple times in case of nested stringified JSON
    for _ in range(2):
        try:
            parsed = json.loads(json_candidate)
            if isinstance(parsed, str):
                json_candidate = parsed
                continue
            return parsed
        except Exception:
            pass

    # Fallback: return plain text if decoding fails
    return {"body": cleaned}


# ---------------- Utility: Extract Recipient ----------------
def extract_recipient(context: str):
    """
    Extracts email address from user text.
    Example: "Send a mail to john@example.com about project update"
    """
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", context)
    if match:
        return match.group(0)
    return None


# ---------------- Utility: AI Email Draft ----------------
def generate_ai_email(context: str) -> dict:
    """
    Generates a professional, polite, and structured email using Groq LLM.
    """
    system_prompt = """
    You are a professional email writing assistant.
    Craft a complete, well-structured email based on the given context.
    Follow these rules strictly:
    - Use a polite, natural, and professional business tone.
    - Begin with a greeting (e.g., 'Hi <Name>,' or 'Hello Team,').
    - Write 2–3 concise, well-formed paragraphs.
    - End with a polite closing (e.g., 'Best regards,' or 'Thank you,').
    - The subject should be clear and concise.
    - Do NOT include markdown, explanations, or backticks.
    - Output ONLY valid JSON in this format:
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
        temperature=0.6,
        max_tokens=500,
    )

    ai_text = completion.choices[0].message.content.strip()
    parsed = safe_parse_json(ai_text)

    # Fallbacks for robustness
    if not parsed.get("subject") or not parsed.get("body"):
        parsed = {"subject": "Automated Email", "body": ai_text}

    return parsed


# ---------------- Utility: Send Email via Brevo ----------------
def send_brevo_email(to_email: str, subject: str, body: str):
    """
    Sends a formatted professional email using Brevo's transactional API.
    """
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    # Well-styled HTML body
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
        "status": "✅ Enhanced AI Email Agent Active",
        "endpoint": "/create_draft (POST)"
    }), 200


@app.route("/create_draft", methods=["POST"])
def create_draft():
    """
    Create an AI-generated professional email and send it via Brevo.
    Automatically detects the recipient from input or request body.
    """
    try:
        data = request.get_json(force=True)
        user_input = data.get("context", "")
        explicit_recipient = data.get("to")

        # Detect recipient dynamically
        recipient = explicit_recipient or extract_recipient(user_input)
        if not recipient:
            return jsonify({"error": "No valid recipient found in the message."}), 400

        # Sanitize input (remove email addresses before sending to AI)
        sanitized_context = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", user_input)

        ai_email = generate_ai_email(sanitized_context)
        subject = ai_email.get("subject", "AI Generated Email").strip()
        body = ai_email.get("body", "Hello,\n\nThis is an AI-generated message.\n\nBest,\nPOS Agent").strip()

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
    port = int(os.getenv("PORT", 10003))  # ✅ Dynamic port for Render
    print(f"🚀 Email Agent running on port {port}")
    app.run(host="0.0.0.0", port=port)
