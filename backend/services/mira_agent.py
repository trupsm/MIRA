# backend/services/mira_agent.py
from flask import Flask, request, jsonify
from supabase import create_client
from twilio.rest import Client as TwilioClient
import openai
import ollama
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import traceback

# Load environment and ensure Ollama host is set for the Python client
load_dotenv()
os.environ["OLLAMA_HOST"] = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

app = Flask(__name__)

# Config / clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        supabase = None
        app.logger.error("Supabase client init error: %s", e)
else:
    supabase = None
    app.logger.warning("Supabase not configured (SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing).")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER")
if TWILIO_SID and TWILIO_TOKEN:
    try:
        twilio = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
    except Exception as e:
        twilio = None
        app.logger.error("Twilio client init error: %s", e)
else:
    twilio = None
    app.logger.warning("Twilio not configured (TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN missing).")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")  # default to a lightweight model

# Templates
SMS_TEMPLATES = {
    "short": "Hi {contact_name}, this is a private MIRA alert. Your contact may be struggling emotionally. Please check in when you can. (Confidential)",
    "moderate": "Hi {contact_name}, confidential MIRA alert: Your contact has expressed distress. Excerpt: \"{excerpt}\". Please reach out privately when possible.",
    "urgent": "URGENT (confidential): {contact_name}, your contact may be at immediate risk. Excerpt: \"{excerpt}\". Please call them now."
}

# Keyword fallback
SEVERE_PHRASES = ["i want to die", "kill myself", "end my life", "i have a plan", "going to do it", "i'm going to kill myself"]
MODERATE_PHRASES = ["can't go on", "tired of living", "hopeless", "nothing matters", "want to disappear", "i can't take this anymore"]

# Helpers
def query_medgemma(prompt: str) -> str:
    """
    Try Ollama first. If Ollama fails and OpenAI key exists, use OpenAI as a fallback.
    Always return a short friendly fallback message if both fail.
    """
    system_prompt = (
        "You are Dr. Mira, a calm, supportive AI therapist. "
        "Speak warmly and compassionately, reflect the user's emotions, "
        "and always ask one gentle open-ended question to help them express more."
    )

    # Attempt Ollama
    try:
        app.logger.info("🧠 Sending to Ollama model: %s", OLLAMA_MODEL)
        r = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            options={"num_predict": 300, "temperature": 0.7, "top_p": 0.9},
        )
        app.logger.debug("Ollama response raw: %s", r)
        return r.get("message", {}).get("content", "").strip() or "I'm sorry, I'm having trouble right now. Your feelings are important."
    except Exception as e:
        app.logger.error("❌ Ollama error: %s", e)
        app.logger.debug(traceback.format_exc())

    # Fallback to OpenAI if available
    if OPENAI_API_KEY:
        try:
            app.logger.info("🔁 Falling back to OpenAI (gpt-4o-mini)")
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=250,
                temperature=0.7
            )
            out = resp.choices[0].message.content.strip()
            app.logger.info("✅ OpenAI fallback response obtained")
            return out
        except Exception as e2:
            app.logger.error("❌ OpenAI fallback error: %s", e2)
            app.logger.debug(traceback.format_exc())

    # Final user-facing fallback
    return "I'm sorry, I'm having trouble right now. Your feelings are important."

def classify_severity_with_openai(text: str):
    # fallback to keywords if OpenAI not configured
    if not OPENAI_API_KEY:
        t = text.lower()
        if any(p in t for p in SEVERE_PHRASES):
            return {"label": "severe", "score": 0.95}
        if any(p in t for p in MODERATE_PHRASES):
            return {"label": "moderate", "score": 0.7}
        return {"label": "none", "score": 0.0}

    prompt = (
        "You are a safety classifier. Given the message, return JSON: {\"label\":\"none|moderate|severe\",\"score\":0.0-1.0}\n\n"
        f"Message: \"{text}\"\n\nReturn ONLY JSON."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.0
        )
        out = resp.choices[0].message.content.strip()
        parsed = json.loads(out)
        label = parsed.get("label", "none")
        score = float(parsed.get("score", 0.0))
        return {"label": label, "score": max(0.0, min(1.0, score))}
    except Exception as e:
        app.logger.error("OpenAI classifier error: %s", e)
        app.logger.debug(traceback.format_exc())
        t = text.lower()
        if any(p in t for p in SEVERE_PHRASES):
            return {"label": "severe", "score": 0.95}
        if any(p in t for p in MODERATE_PHRASES):
            return {"label": "moderate", "score": 0.7}
        return {"label": "none", "score": 0.0}

def get_primary_contact(user_id):
    if not supabase:
        return None
    try:
        r = supabase.table("emergency_contacts").select("*").eq("user_id", user_id).eq("is_primary", True).limit(1).execute()
        # supabase-py returns dict with 'data' in some versions, in others it's directly .data
        data = getattr(r, "data", None) or r.get("data") if isinstance(r, dict) else r.data if hasattr(r, "data") else None
        if not data:
            # fallback: r may be a list
            return None
        return data[0] if len(data) else None
    except Exception as e:
        app.logger.error("Supabase get_primary_contact error: %s", e)
        app.logger.debug(traceback.format_exc())
        return None

def send_sms(phone, template_key, name, excerpt):
    if not twilio:
        raise RuntimeError("Twilio client not configured")
    template = SMS_TEMPLATES.get(template_key, SMS_TEMPLATES["moderate"])
    body = template.format(contact_name=name or "there", excerpt=excerpt)
    try:
        msg = twilio.messages.create(body=body, from_=TWILIO_FROM, to=phone)
        app.logger.info("Twilio SMS SID: %s", getattr(msg, "sid", None))
        return getattr(msg, "sid", None)
    except Exception as e:
        app.logger.error("Twilio send_sms error: %s", e)
        app.logger.debug(traceback.format_exc())
        raise

def place_call(phone):
    if not twilio:
        raise RuntimeError("Twilio client not configured")
    try:
        call = twilio.calls.create(to=phone, from_=TWILIO_FROM, url="http://demo.twilio.com/docs/voice.xml")
        app.logger.info("Twilio CALL SID: %s", getattr(call, "sid", None))
        return getattr(call, "sid", None)
    except Exception as e:
        app.logger.error("Twilio place_call error: %s", e)
        app.logger.debug(traceback.format_exc())
        raise

def log_chat(user_id, sender, message):
    if not supabase:
        app.logger.debug("Supabase not configured — skipping chat_history log")
        return
    try:
        supabase.table("chat_history").insert([{
            "user_id": user_id, "sender": sender, "message": message, "created_at": datetime.utcnow().isoformat()
        }]).execute()
    except Exception as e:
        app.logger.error("Supabase insert chat_history error: %s", e)
        app.logger.debug(traceback.format_exc())

def log_crisis(user_id, message, model_response, severity_label, severity_score, sms_sent, call_initiated, contact):
    if not supabase:
        app.logger.debug("Supabase not configured — skipping crisis_logs insert")
        return
    try:
        supabase.table("crisis_logs").insert([{
            "user_id": user_id,
            "message": message,
            "model_response": model_response,
            "severity": severity_label,
            "detected_at": datetime.utcnow().isoformat(),
            "sms_sent": sms_sent,
            "call_initiated": call_initiated,
            "contact_name": contact.get("name") if contact else None,
            "contact_number": contact.get("phone_number") if contact else None,
            "action_taken": ("call" if call_initiated else ("sms" if sms_sent else None)),
            "meta": json.dumps({"severity_score": severity_score})
        }]).execute()
    except Exception as e:
        app.logger.error("Supabase insert crisis_logs error: %s", e)
        app.logger.debug(traceback.format_exc())

# Routes
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "mira_agent"})

@app.route('/api/mira_chat', methods=['POST'])
def mira_chat():
    data = request.json or {}
    user_id = data.get("user_id")
    message = (data.get("message") or "").strip()
    if not user_id or not message:
        return jsonify({"error": "user_id and message required"}), 400

    # log user message
    log_chat(user_id, "user", message)

    # build prompt (could include recent moods/memory)
    prompt = f"User says: {message}\nRespond empathetically and ask a gentle question."

    # AI reply
    model_reply = query_medgemma(prompt)
    log_chat(user_id, "mira", model_reply)

    # classify severity
    cl = classify_severity_with_openai(message)
    label, score = cl.get("label", "none"), float(cl.get("score", 0.0))

    sms_sent = False
    call_initiated = False
    contact = None

    # thresholds (tunable)
    SMS_THRESHOLD = 0.45
    CALL_THRESHOLD = 0.80

    if label in ("moderate", "severe") or score >= SMS_THRESHOLD:
        contact = get_primary_contact(user_id)
        if contact and contact.get("opted_in"):
            excerpt = (message[:120] + "...") if len(message) > 120 else message
            template_key = "urgent" if (label == "severe" or score >= CALL_THRESHOLD) else "moderate"
            try:
                sid_sms = send_sms(contact["phone_number"], template_key, contact.get("name"), excerpt)
                sms_sent = True if sid_sms else False
                if (label == "severe" or score >= CALL_THRESHOLD) and contact.get("allow_auto_call"):
                    sid_call = place_call(contact["phone_number"])
                    call_initiated = True if sid_call else False
            except Exception as e:
                app.logger.error("Twilio notify error: %s", e)
                app.logger.debug(traceback.format_exc())
        else:
            app.logger.info("No primary contact or opted_in false for user_id: %s", user_id)

        # Log crisis (safe even if Twilio failed or contact missing)
        log_crisis(user_id, message, model_reply, label, score, sms_sent, call_initiated, contact)

    return jsonify({
        "response": model_reply,
        "crisis_detected": label != "none",
        "severity": label,
        "severity_score": score,
        "contact_notified": sms_sent or call_initiated
    })

if __name__ == '__main__':
    # Run on port 8001
    app.run(host='0.0.0.0', port=8001, debug=True)
