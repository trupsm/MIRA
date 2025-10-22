// backend/routes/chat.js
const express = require('express');
const router = express.Router();
const fetch = require('node-fetch');
const auth = require('../middleware/auth');
require('dotenv').config();

const MIRA_AGENT_URL = process.env.MIRA_AGENT_URL || 'http://localhost:8001/api/mira_chat';

/**
 * POST /api/chat
 * Requires: Authorization Bearer <JWT>
 * Body: { "message": "..." }
 * Response: { response, crisis_detected, severity, contact_notified }
 */
router.post('/', auth, async (req, res) => {
  const message = req.body.message?.trim();
  const userId = req.user?.id;

  if (!message)
    return res.status(400).json({ message: 'Message required' });

  try {
    // 🔹 Directly forward to Mira Agent (Flask)
    const r = await fetch(MIRA_AGENT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, message })
    });

    // Handle connection or parsing errors gracefully
    if (!r.ok) {
      const text = await r.text();
      console.error('❌ Mira agent error:', text);
      return res.status(500).json({
        message: 'Chat failed: Mira agent unreachable',
        error: text
      });
    }

    const data = await r.json();

    // ✅ Send back structured response
    res.json({
      message: 'MIRA chat success',
      response: data.response,
      crisis_detected: data.crisis_detected,
      severity: data.severity,
      severity_score: data.severity_score,
      contact_notified: data.contact_notified
    });
  } catch (err) {
    console.error('❌ Chat route error:', err);
    res.status(500).json({ message: 'Chat failed', error: err.message });
  }
});

module.exports = router;