from flask import Flask, request, jsonify
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import pytz

# ---------------------- ENV ----------------------
load_dotenv()
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
TASK_DB_ID = os.getenv("NOTION_TASK_DATABASE_ID")
XP_LEDGER_DB_ID = os.getenv("NOTION_XP_LEDGER_ID")
XP_AGENT_PORT = int(os.getenv("XP_AGENT_PORT", 10001))

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ---------------------- APP ----------------------
app = Flask(__name__)

# ---------------------- HELPER: Calculate XP ----------------------
def calculate_dynamic_xp(task_name: str, due_date: str | None):
    """
    Dynamically calculates XP based on urgency and task difficulty.
    (Later this will also use WHOOP recovery + strain data)
    """
    base_xp = 10

    # Add urgency bonus
    if due_date:
        try:
            due = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
            now = datetime.now(pytz.UTC)
            hours_left = (due - now).total_seconds() / 3600
            if hours_left < 6:
                base_xp += 20  # very urgent
            elif hours_left < 24:
                base_xp += 10  # moderately urgent
        except Exception:
            pass

    # Add complexity bonus based on task keywords
    if any(keyword in task_name.lower() for keyword in ["report", "presentation", "analysis", "summary"]):
        base_xp += 15
    elif any(keyword in task_name.lower() for keyword in ["email", "call", "reminder"]):
        base_xp += 5

    return base_xp

# ---------------------- WHOOP PLACEHOLDERS ----------------------
def get_whoop_recovery():
    """Mock WHOOP recovery value (0–100)."""
    return 85

def adjust_xp_with_whoop(xp):
    """Adjust XP dynamically based on WHOOP recovery."""
    recovery = get_whoop_recovery()
    if recovery < 40:
        xp *= 0.8
    elif recovery > 80:
        xp *= 1.1
    return round(xp)

# ---------------------- HELPER: Find Task ID ----------------------
def get_task_page_id(task_name):
    """
    Search for a task in the Task Database by its name.
    Returns the page ID if found, else None.
    """
    url = f"https://api.notion.com/v1/databases/{TASK_DB_ID}/query"
    query = {
        "filter": {
            "property": "Task",
            "title": {"equals": task_name}
        }
    }
    response = requests.post(url, headers=headers, json=query)
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            return results[0]["id"]
    print("⚠️ Task not found in Task Database:", task_name)
    return None

# ---------------------- HELPER: Add XP Record ----------------------
def add_xp_to_ledger(task_name, avatar, xp_points, reason):
    """
    Adds a new XP record in the XP Ledger database in Notion.
    Links to the Task Database using relation.
    """
    url = "https://api.notion.com/v1/pages"
    timestamp = datetime.now(pytz.UTC).isoformat()

    task_id = get_task_page_id(task_name)

    # Build XP Ledger entry
    body = {
        "parent": {"database_id": XP_LEDGER_DB_ID},
        "properties": {
            "XP Entry": {"title": [{"text": {"content": f"XP for {task_name}"}}]},
            "Avatar": {"select": {"name": avatar}},
            "XP Awarded": {"number": xp_points},
            "Reason": {"rich_text": [{"text": {"content": reason}}]},
            "Timestamp": {"date": {"start": timestamp}},
        },
    }

    # If task relation exists, attach it
    if task_id:
        body["properties"]["Task"] = {"relation": [{"id": task_id}]}

    r = requests.post(url, headers=headers, json=body)
    if r.status_code not in [200, 201]:
        print("❌ Failed to add XP to ledger:", r.text)
    else:
        print(f"✅ XP entry created for {task_name} ({xp_points} XP)")
    return r.status_code

# ---------------------- ROUTES ----------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "XP Agent running ✅",
        "version": "1.2",
        "endpoints": ["/award_xp"]
    }), 200

@app.route("/award_xp", methods=["POST"])
def award_xp():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    task_name = data.get("task_name", "Untitled Task")
    avatar = data.get("avatar", "Producer")
    due_date = data.get("due_date")
    reason = data.get("reason", "Task Completed")

    xp_points = calculate_dynamic_xp(task_name, due_date)
    xp_points = adjust_xp_with_whoop(xp_points)
    status = add_xp_to_ledger(task_name, avatar, xp_points, reason)

    return jsonify({
        "task": task_name,
        "xp_awarded": xp_points,
        "reason": reason,
        "whoop_adjusted": True,
        "status": "XP logged" if status in [200, 201] else "Error logging XP"
    }), 200 if status in [200, 201] else 500

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    print(f"🚀 XP Agent running on port {XP_AGENT_PORT}")
    app.run(host="0.0.0.0", port=XP_AGENT_PORT)
