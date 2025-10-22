
from flask import Flask, request, jsonify
from supabase import create_client
from twilio.rest import Client as TwilioClient
import openai
import ollama
import os
import json
import re
import time
from datetime import datetime
from dotenv import load_dotenv
import traceback

# ------------------ CONFIG ------------------

load_dotenv()
os.environ["OLLAMA_HOST"] = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

app = Flask(__name__)

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        app.logger.error("❌ Supabase init error: %s", e)
else:
    app.logger.warning("⚠️ Supabase not configured")

# Twilio config
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER")
twilio = None
if TWILIO_SID and TWILIO_TOKEN:
    try:
        twilio = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
    except Exception as e:
        app.logger.error("❌ Twilio init error: %s", e)
else:
    app.logger.warning("⚠️ Twilio not configured")

# OpenAI config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# Default Ollama model
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")

# ------------------ HELPER PROMPTS ------------------

def get_mira_prompt():
    return (
        "You are Mira — a warm, deeply empathetic mental health companion. "
        "You listen closely, reflect emotions, and respond like a trusted friend. "
        "You never give medical advice, you never dismiss pain, and you never use poetic or religious phrases. "
        "When someone expresses hopelessness or thoughts of death, you respond with gentle validation and grounded empathy. "
        "Keep replies 2–4 sentences, always ending with one gentle, open-ended question. "
        "Example: If someone says 'I don’t want to wake up anymore', you might say:\n"
        "'It sounds like you’re feeling completely drained and wishing everything could stop for a while. "
        "That’s such a painful place to be — and you don’t have to face it alone. What’s been feeling most unbearable lately?'"
    )

# ------------------ SEVERITY CLASSIFICATION ------------------

SEVERE_KEYWORDS = [
    "kill myself", "end my life", "suicide", "take my own life",
    "i want to die", "no reason to live", "goodbye forever",
    "i have a plan", "ready to die", "done with life", "tonight is the night"
]

MODERATE_KEYWORDS = [
    "tired of living", "hopeless", "nothing matters", "can't go on",
    "worthless", "wish i could sleep forever", "want to disappear",
    "emotionally exhausted", "give up", "done with everything"
]

def classify_severity(text: str):
    """Hybrid rule + AI-based classifier."""
    text_lower = text.lower().strip()
    label, score = "none", 0.0

    # Keyword detection
    if any(phrase in text_lower for phrase in SEVERE_KEYWORDS):
        label, score = "severe", 0.95
    elif any(phrase in text_lower for phrase in MODERATE_KEYWORDS):
        label, score = "moderate", 0.7

    # Fallback to AI if OpenAI is available
    if OPENAI_API_KEY:
        try:
            prompt = (
                "You are a mental health crisis classifier. "
                "Analyze the following message and return only JSON: "
                '{"label": "none|moderate|severe", "score": 0.0-1.0}.\n'
                f'Message: "{text}"'
            )
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.2
            )
            content = resp.choices[0].message.content.strip()
            parsed = json.loads(content)
            label = parsed.get("label", label)
            score = float(parsed.get("score", score))
        except Exception as e:
            app.logger.warning(f"⚠️ AI classification fallback: {e}")

    action_map = {
        "none": "monitor_only",
        "moderate": "send_sms",
        "severe": "emergency_call"
    }

    app.logger.info(f"🧠 Severity: {label} ({score})")
    return {"label": label, "score": score, "action": action_map[label]}

# ------------------ CHAT GENERATION ------------------

def query_mira(user_message: str) -> str:
    """Generate Mira's empathetic response using Ollama or OpenAI."""
    prompt = get_mira_prompt()
    try:
        r = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            options={"temperature": 0.7, "num_predict": 200}
        )
        reply = r.get("message", {}).get("content", "").strip()
        if reply.lower().startswith(("mira:", "assistant:", "ai:")):
            reply = reply.split(":", 1)[-1].strip()
        return reply or "That sounds really painful to feel. What’s been weighing on you most?"
    except Exception as e:
        app.logger.error("⚠️ Ollama error: %s", e)
        app.logger.debug(traceback.format_exc())

    if OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=180,
                temperature=0.7
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            app.logger.error("⚠️ OpenAI fallback error: %s", e)

    return "That sounds really heavy to carry. You don’t have to go through this alone — what’s been the hardest part lately?"

# ------------------ TWILIO HELPERS ------------------

SMS_TEMPLATES = {
    "moderate": "Hi {name}, Mira alert: your contact is in distress. Excerpt: \"{excerpt}\". Please reach out when possible.",
    "urgent": "🚨 URGENT: {name}, your contact may be at immediate risk. Excerpt: \"{excerpt}\". Please contact them or emergency services now."
}

def send_sms(phone, template_key, name, excerpt):
    """Send SMS with retries."""
    if not twilio:
        raise RuntimeError("Twilio not configured")
    body = SMS_TEMPLATES[template_key].format(name=name or "there", excerpt=excerpt)
    for i in range(3):
        try:
            msg = twilio.messages.create(body=body, from_=TWILIO_FROM, to=phone)
            app.logger.info(f"📩 SMS sent to {phone}, SID: {msg.sid}")
            return msg.sid
        except Exception as e:
            app.logger.warning(f"Retry {i+1} failed: {e}")
            time.sleep(2)
    return None

def place_call(phone):
    """Trigger emergency call via Twilio."""
    if not twilio:
        raise RuntimeError("Twilio not configured")
    call = twilio.calls.create(to=phone, from_=TWILIO_FROM, url="http://demo.twilio.com/docs/voice.xml")
    app.logger.info(f"📞 Emergency call placed to {phone}")
    return call.sid

# ------------------ DATABASE HELPERS ------------------

def get_primary_contact(user_id):
    if not supabase:
        return None
    try:
        res = supabase.table("emergency_contacts").select("*").eq("user_id", user_id).eq("is_primary", True).limit(1).execute()
        data = getattr(res, "data", None)
        return data[0] if data else None
    except Exception as e:
        app.logger.error("⚠️ Supabase contact fetch error: %s", e)
        return None

def log_chat(user_id, sender, message):
    if not supabase:
        return
    try:
        supabase.table("chat_history").insert([{
            "user_id": user_id,
            "sender": sender,
            "message": message,
            "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        }]).execute()
    except Exception as e:
        app.logger.error("⚠️ Chat log error: %s", e)

def log_crisis(user_id, message, response, label, score, action, contact):
    if not supabase:
        return
    try:
        supabase.table("crisis_logs").insert([{
            "user_id": user_id,
            "message": message,
            "model_response": response,
            "severity": label,
            "detected_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "sms_sent": action == "send_sms",
            "call_initiated": action == "emergency_call",
            "contact_name": contact.get("name") if contact else None,
            "contact_number": contact.get("phone_number") if contact else None,
            "action_taken": action,
            "meta": json.dumps({"score": score})
        }]).execute()
    except Exception as e:
        app.logger.error("⚠️ Crisis log error: %s", e)

# ------------------ ROUTES ------------------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "mira_agent"})

@app.route("/api/mira_chat", methods=["POST"])
def mira_chat():
    data = request.json or {}
    user_id = data.get("user_id")
    message = (data.get("message") or "").strip()

    if not user_id or not message:
        return jsonify({"error": "user_id and message required"}), 400

    log_chat(user_id, "user", message)

    # Generate response
    response = query_mira(message)
    log_chat(user_id, "mira", response)

    # Detect severity
    severity = classify_severity(message)
    label, score, action = severity["label"], severity["score"], severity["action"]

    sms_sent = False
    call_initiated = False
    contact = get_primary_contact(user_id)
    action_taken = "none"

    # Crisis handling
    if label in ["moderate", "severe"]:
        if contact and str(contact.get("opted_in", "")).lower() in ["true", "1", "yes"]:
            excerpt = message[:120] + "..." if len(message) > 120 else message
            try:
                if action == "send_sms":
                    send_sms(contact["phone_number"], "moderate", contact["name"], excerpt)
                    sms_sent, action_taken = True, "send_sms"
                elif action == "emergency_call":
                    send_sms(contact["phone_number"], "urgent", contact["name"], excerpt)
                    if str(contact.get("allow_auto_call", "")).lower() in ["true", "1", "yes"]:
                        place_call(contact["phone_number"])
                        call_initiated, action_taken = True, "emergency_call"
            except Exception as e:
                app.logger.error(f"❌ Twilio error: {e}")

        log_crisis(user_id, message, response, label, score, action_taken, contact)

    return jsonify({
        "response": response,
        "crisis_detected": label in ["moderate", "severe"],
        "severity": label,
        "severity_score": round(score, 2),
        "action_recommended": action,
        "action_taken": action_taken,
        "contact_notified": sms_sent or call_initiated,
        "sms_sent": sms_sent,
        "call_initiated": call_initiated
    })


# ------------------ DEBUG ROUTE ------------------

@app.route('/_debug/contact/<user_id>', methods=['GET'])
def debug_contact(user_id):
    """Temporary route to verify Supabase -> Flask -> Twilio contact flow."""
    try:
        contact = get_primary_contact(user_id)
        if not contact:
            return jsonify({"found": False, "message": "No contact found for user"}), 404
        return jsonify({"found": True, "contact": contact}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------ MAIN ------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
