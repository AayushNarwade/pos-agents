from flask import Flask, request, jsonify
import os
import re
import json
from dotenv import load_dotenv
import google.generativeai as genai
from groq import Groq

# ---------------------
# INIT
# ---------------------
load_dotenv()
app = Flask(__name__)

# Gemini setup
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Groq setup
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------
# Utility: Clean Model Output
# ---------------------
def clean_json_response(raw_text: str):
    """
    Cleans and parses JSON-like text returned by LLMs.
    Handles truncated or fenced outputs gracefully.
    """
    import re, json

    if not raw_text:
        return {}

    # Remove ```json fences
    cleaned = re.sub(r"^```(?:json)?", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```$", "", cleaned.strip())

    # Try to extract the JSON-like portion
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return {"raw_text": cleaned}

    json_candidate = match.group(0)

    # Auto-fix: if closing bracket is missing, append one
    if json_candidate.count("{") > json_candidate.count("}"):
        json_candidate += "}"

    try:
        return json.loads(json_candidate)
    except json.JSONDecodeError:
        # Attempt to parse partial JSON content
        fixed = json_candidate.replace("\n", "").replace("\t", "")
        fixed = re.sub(r",\s*]", "]", fixed)
        fixed = re.sub(r",\s*}", "}", fixed)
        try:
            return json.loads(fixed)
        except Exception:
            return {"raw_text": cleaned}


# ---------------------
# Research Functions
# ---------------------
def research_with_gemini(query):
    prompt = f"""
You are a professional research assistant.
Summarize the following topic concisely using general publicly available knowledge.
Avoid giving medical, legal, or financial advice.

Topic: "{query}"

Respond ONLY in the following JSON format:
{{
  "executive_summary": ["point1", "point2", "point3"],
  "key_findings": ["finding1", "finding2", "finding3"],
  "notable_sources": ["source 1 (if known)", "source 2 (if known)"],
  "recommended_next_steps": ["next step 1", "next step 2"]
}}
"""

    model = genai.GenerativeModel("models/gemini-2.5-flash")

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 800,
            },
        )

        if not response or not getattr(response, "text", None):
            reason = getattr(response.candidates[0], "finish_reason", "unknown")
            raise RuntimeError(f"Gemini blocked output (reason: {reason})")

        return clean_json_response(response.text)

    except Exception as e:
        raise RuntimeError(f"Gemini failed: {str(e)}")


def research_with_groq(query):
    prompt = f"""
You are a factual research assistant.
Summarize the following topic concisely.

Topic: "{query}"

Respond ONLY in JSON format:
{{
  "executive_summary": ["point1", "point2", "point3"],
  "key_findings": ["finding1", "finding2", "finding3"],
  "notable_sources": ["source 1 (if known)", "source 2 (if known)"],
  "recommended_next_steps": ["next step 1", "next step 2"]
}}
"""

    completion = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=800,
    )

    return clean_json_response(completion.choices[0].message.content)

# ---------------------
# Flask Routes
# ---------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Research Agent (Gemini + Groq Hybrid, Clean JSON) active"})


@app.route("/research", methods=["POST"])
def research():
    data = request.get_json()
    query = data.get("query")

    if not query:
        return jsonify({"error": "Missing query"}), 400

    try:
        print(f"🧠 Using Gemini for query: {query}")
        summary = research_with_gemini(query)
        return jsonify({
            "query": query,
            "summary": summary,
            "model_used": "Gemini 2.5 Flash"
        })

    except Exception as gemini_error:
        print(f"⚠️ Gemini failed — switching to Groq: {gemini_error}")
        try:
            summary = research_with_groq(query)
            return jsonify({
                "query": query,
                "summary": summary,
                "model_used": "LLaMA 3.3 70B (Groq Fallback)"
            })
        except Exception as groq_error:
            print(f"❌ Both Gemini and Groq failed: {groq_error}")
            return jsonify({
                "error": f"Both Gemini and Groq failed: {str(groq_error)}"
            }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
