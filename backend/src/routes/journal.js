import express from "express";
import dotenv from "dotenv";
import supabase from "../config/supabase.js";
import auth from "../middleware/auth.js";
import OpenAI from "openai";
import Sentiment from "sentiment";

dotenv.config();

const router = express.Router();
const sentiment = new Sentiment();
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

/**
 * POST /api/journal
 * Create a journal entry with emotion + crisis detection
 */
router.post("/", auth, async (req, res) => {
  const { content } = req.body;
  if (!content)
    return res.status(400).json({ message: "Journal content is required" });

  try {
    // 🚨 Crisis Keyword Detection
    const crisisKeywords = [
      "suicide",
      "kill myself",
      "end my life",
      "die",
      "hopeless",
      "worthless",
      "can’t go on",
      "tired of living",
      "cut myself",
      "hurt myself",
      "no reason to live",
      "goodbye forever",
      "better off dead",
    ];
    const crisisDetected = crisisKeywords.some((kw) =>
      content.toLowerCase().includes(kw)
    );

    if (crisisDetected) {
      const { data, error } = await supabase
        .from("journals")
        .insert([
          {
            user_id: req.user.id,
            content,
            summary:
              "⚠️ Crisis indicators detected. Please reach out to someone you trust or contact emergency support immediately.",
            emotion: "crisis",
          },
        ])
        .select();

      if (error) throw error;
      return res.status(201).json({
        message: "Journal saved with crisis flag",
        emotion_detected: "crisis",
        summary: data[0].summary,
        journal: data[0],
      });
    }

    // 🧠 Sentiment Analysis
    const emotionScore = sentiment.analyze(content).score;
    let emotion = "neutral";
    if (emotionScore > 2) emotion = "positive";
    else if (emotionScore < -2) emotion = "negative";

    // 🤖 AI Reflection using OpenAI
    const prompt = `
You are a compassionate journaling assistant.

Analyze the following journal entry written in English:
1. Determine the user's emotional tone (happy, sad, anxious, calm, etc.).
2. Write a short 2–3 sentence empathetic reflection.
3. Avoid advice or robotic tone. Be gentle and understanding.

Return JSON:
{
  "emotion": "<emotion>",
  "summary": "<reflective summary>"
}

Journal:
"""${content}"""
`;

    const aiResponse = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
      temperature: 0.7,
      max_tokens: 300,
    });

    const rawText = aiResponse.choices[0].message.content.trim();
    let summary = "";
    let emotionAI = emotion;

    try {
      const parsed = JSON.parse(rawText);
      emotionAI = parsed.emotion || emotion;
      summary = parsed.summary || rawText;
    } catch {
      summary = rawText;
    }

    // 💾 Save to Supabase
    const { data, error } = await supabase
      .from("journals")
      .insert([
        {
          user_id: req.user.id,
          content,
          summary,
          emotion: emotionAI,
        },
      ])
      .select();

    if (error) throw error;

    res.status(201).json({
      message: "Journal added successfully",
      emotion_detected: emotionAI,
      summary,
      journal: data[0],
    });
  } catch (err) {
    console.error("❌ Journal error:", err.message);
    res.status(500).json({
      message: "Failed to process journal",
      error: err.message,
    });
  }
});

/**
 * GET /api/journal
 * Retrieve all journals for the logged-in user
 */
router.get("/", auth, async (req, res) => {
  const { data, error } = await supabase
    .from("journals")
    .select("*")
    .eq("user_id", req.user.id)
    .order("created_at", { ascending: false });

  if (error)
    return res
      .status(500)
      .json({ message: "Failed to fetch journals", error: error.message });

  res.json({ journals: data });
});

export default router;
