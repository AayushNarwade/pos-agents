from flask import Flask, request, jsonify
import os, requests, json, traceback
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
app = Flask(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "pos-agent@mvp.com")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

def generate_ai_email(context: str):
    system_prompt = """
    You are a helpful email assistant. Return only JSON:
    {"subject": "<subject>", "body": "<email body>"}
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
        return json.loads(completion.choices[0].message.content.strip())
    except:
        return {"subject": "AI Draft Email", "body": completion.choices[0].message.content.strip()}

def send_brevo_email(to_email, subject, body):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {"sender": {"name": "POS AI Agent", "email": SENDER_EMAIL}, "to": [{"email": to_email}],
               "subject": subject, "textContent": body}
    response = requests.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "✅ AI Email Agent Running (Brevo)"}), 200

@app.route("/create_draft", methods=["POST"])
def create_draft():
    try:
        data = request.get_json(force=True)
        recipient, context = data.get("to"), data.get("context")
        if not recipient or not context:
            return jsonify({"error": "Missing 'to' or 'context'"}), 400

        ai_email = generate_ai_email(context)
        subject, body = ai_email["subject"], ai_email["body"]
        brevo_response = send_brevo_email(recipient, subject, body)

        email_link = f"https://app.brevo.com/email/{brevo_response.get('messageId', '')}"

        return jsonify({
            "status": "✅ Email Sent",
            "to": recipient,
            "subject": subject,
            "body_preview": body[:200],
            "brevo_response": brevo_response,
            "email_link": email_link
        }), 200
    except Exception as e:
        print("❌ Error:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10003))
    app.run(host="0.0.0.0", port=port)
