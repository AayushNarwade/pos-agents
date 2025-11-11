from flask import Flask, request, jsonify
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import pytz
import json
import math

# Optional Groq client for reasoning
try:
    from groq import Groq
except Exception:
    Groq = None

# ---------------- Setup ----------------
app = Flask(__name__)
load_dotenv()
IST = pytz.timezone("Asia/Kolkata")

# ---------------- ENV ----------------
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_TASK_DATABASE_ID = os.getenv("NOTION_TASK_DATABASE_ID")
NOTION_XP_LEDGER_ID = os.getenv("NOTION_XP_LEDGER_ID")  # optional
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

PORT = int(os.getenv("PORT", 10003))
NOTION_BASE = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

groq_client = Groq(api_key=GROQ_API_KEY) if (GROQ_API_KEY and Groq is not None) else None


# ---------------- Helpers ----------------
def notion_query_open_tasks():
    """Fetch tasks in 'To Do' or 'In Progress' status."""
    url = f"{NOTION_BASE}/databases/{NOTION_TASK_DATABASE_ID}/query"
    body = {
        "filter": {
            "or": [
                {"property": "Status", "select": {"equals": "To Do"}},
                {"property": "Status", "select": {"equals": "In Progress"}}
            ]
        }
    }
    r = requests.post(url, headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json().get("results", [])


def extract_task_summary(page):
    """Extract summary info from a Notion page."""
    props = page.get("properties", {})
    task = props.get("Task", {}).get("title", [])
    title = "".join([t.get("plain_text", "") for t in task]).strip()

    context = ""
    if "Context" in props:
        rt = props["Context"].get("rich_text", [])
        context = "".join([t.get("plain_text", "") for t in rt]).strip()

    due_date = None
    if "Due Date" in props and props["Due Date"].get("date"):
        dd = props["Due Date"]["date"].get("start")
        if dd:
            try:
                due_date = datetime.fromisoformat(dd)
            except Exception:
                pass

    xp = props.get("XP", {}).get("number")
    return {
        "id": page["id"],
        "title": title,
        "context": context,
        "due_date": due_date,
        "xp": xp
    }


def compute_xp_from_due(due_date):
    """Compute XP reward based on timing difference."""
    base_xp = 15
    now = datetime.now(IST)

    if not due_date:
        return base_xp

    if due_date.tzinfo is None:
        due_date = IST.localize(due_date)
    delta_hours = (due_date - now).total_seconds() / 3600.0

    if delta_hours > 0:  # Early
        bonus = min(5, int(delta_hours // 24))
        xp = base_xp + bonus
    else:  # Late
        days_late = math.floor(abs(delta_hours) / 24)
        penalty = days_late * 3
        xp = max(2, base_xp - penalty)

    return int(min(max(1, xp), 50))


def patch_notion_task(page_id, xp):
    """Update XP and mark task as Completed."""
    url = f"{NOTION_BASE}/pages/{page_id}"
    body = {
        "properties": {
            "XP": {"number": xp},
            "Status": {"select": {"name": "Completed"}}
        }
    }
    r = requests.patch(url, headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def groq_match_task(message, candidates):
    """Use Groq reasoning or heuristic to find best task match."""
    if not candidates:
        return None

    candidate_text = "\n".join(
        [f"{i+1}. {c['title']} | context: {c['context'] or 'none'}" for i, c in enumerate(candidates)]
    )

    prompt = f"""
    You are an intelligent task matcher.
    Choose which of the following tasks best matches the user's completion message.
    Return ONLY valid JSON:
    {{"index": <1-based index>, "reason": "<short reason>"}}

    Tasks:
    {candidate_text}

    Message: "{message}"
    """

    if groq_client:
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.0,
                max_tokens=256,
            )
            raw = completion.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
            raw_json = raw[raw.find("{"):raw.rfind("}")+1]
            data = json.loads(raw_json)
            idx = int(data.get("index", 0)) - 1
            if 0 <= idx < len(candidates):
                return {"task": candidates[idx], "reason": data.get("reason", "")}
        except Exception as e:
            print("⚠️ Groq error:", e)

    # fallback heuristic
    msg = message.lower()
    best = None
    for c in candidates:
        score = 0
        if c["title"] and c["title"].lower() in msg:
            score += 10
        if c["context"] and any(w.lower() in msg for w in c["context"].split()):
            score += 3
        if score > 0 and (best is None or score > best[0]):
            best = (score, c)
    if best:
        return {"task": best[1], "reason": "Heuristic match"}
    return None


def log_to_ledger(action_name, xp, source):
    """Optional XP ledger logging."""
    if not NOTION_XP_LEDGER_ID:
        return None
    try:
        payload = {
            "parent": {"database_id": NOTION_XP_LEDGER_ID},
            "properties": {
                "Action": {"title": [{"text": {"content": action_name}}]},
                "XP Earned": {"number": xp},
                "Source": {"rich_text": [{"text": {"content": source}}]},
                "Timestamp": {"date": {"start": datetime.now(IST).isoformat()}}
            }
        }
        resp = requests.post(f"{NOTION_BASE}/pages", headers=HEADERS, json=payload, timeout=10)
        if resp.status_code in [200, 201]:
            print(f"🪙 Logged {xp} XP for '{action_name}'")
            return True
    except Exception as e:
        print("⚠️ Ledger logging failed:", e)
    return False


# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "✅ XP Agent v5 Running (Reasoning-Only Mode)"}), 200


@app.route("/award_xp", methods=["POST"])
def award_xp():
    try:
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        source = data.get("source", "Parent Agent")

        if not message:
            return jsonify({"error": "Missing 'message'"}), 400

        pages = notion_query_open_tasks()
        tasks = [extract_task_summary(p) for p in pages]
        if not tasks:
            return jsonify({"status": "no_open_tasks"}), 200

        print("🔍 Matching against open tasks:")
        for t in tasks:
            print(f"• {t['title']} (context: {t['context']})")

        match = groq_match_task(message, tasks)
        if not match:
            return jsonify({"status": "no_match", "message": "No matching task found"}), 200

        matched_task = match["task"]
        reason = match["reason"]
        xp = compute_xp_from_due(matched_task["due_date"])
        patch_resp = patch_notion_task(matched_task["id"], xp)
        log_to_ledger(matched_task["title"], xp, source)

        return jsonify({
            "status": "✅ XP Awarded",
            "matched_task": matched_task["title"],
            "reason": reason,
            "xp": xp,
            "notion_id": matched_task["id"],
            "notion_update": patch_resp
        }), 200

    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"error": str(e)}), 500


# ---------------- Main ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10003))  # Render injects PORT dynamically
    print(f"🚀 XP Agent v5 running on port {port}")
    app.run(host="0.0.0.0", port=port)

