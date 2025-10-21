// backend/src/routes/chat.js
const express = require('express');
const router = express.Router();
const supabase = require('../config/supabase');
const fetch = require('node-fetch');
const auth = require('../middleware/auth');
require('dotenv').config();

const MIRA_AGENT_URL = process.env.MIRA_AGENT_URL || 'http://localhost:8001/api/mira_chat';

// POST /api/chat
router.post('/', auth, async (req, res) => {
  const user = req.user;
  const message = req.body.message?.trim();

  if (!message) {
    return res.status(400).json({ message: 'Message required' });
  }

  try {
    // Step 1️⃣ — Log user's message
    await supabase.from('chat_history').insert([
      { user_id: user.id, sender: 'user', message }
    ]);

    // Step 2️⃣ — Forward message to Python MIRA agent
    const r = await fetch(MIRA_AGENT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: user.id, message })
    });

    // Step 3️⃣ — Safely parse response (avoid “Unexpected token <” issue)
    const text = await r.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch (err) {
      console.error('⚠️ MIRA agent returned non-JSON:', text);
      return res.status(502).json({
        message: 'Invalid response from MIRA agent',
        raw: text
      });
    }

    // Step 4️⃣ — Extract response safely
    const miraResponse = data.response || '...';
    const crisisDetected = !!data.crisis_detected;
    const severity = data.severity || 'none';
    const contactNotified = !!data.contact_notified;

    // Step 5️⃣ — Log assistant’s reply
    await supabase.from('chat_history').insert([
      { user_id: user.id, sender: 'mira', message: miraResponse }
    ]);

    // Step 6️⃣ — Optionally log crisis info
    if (crisisDetected) {
      await supabase.from('crisis_logs').insert([
        {
          user_id: user.id,
          message,
          model_response: miraResponse,
          severity,
          detected_at: new Date().toISOString(),
          sms_sent: contactNotified,
          call_initiated: !!data.call_initiated,
          action_taken: data.call_initiated
            ? 'call'
            : contactNotified
            ? 'sms'
            : null
        }
      ]);
    }

    // Step 7️⃣ — Return structured response to frontend
    res.json({
      message: 'MIRA chat success',
      response: miraResponse,
      crisis_detected: crisisDetected,
      severity,
      contact_notified: contactNotified
    });
  } catch (err) {
    console.error('💥 Chat route error:', err);
    res.status(500).json({
      message: 'Chat failed',
      error: err.message
    });
  }
});

module.exports = router;
