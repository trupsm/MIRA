import express from "express";
import fs from "fs";
import dotenv from "dotenv";
import { GoogleGenerativeAI } from "@google/generative-ai";

dotenv.config();
const router = express.Router();

// Initialize Gemini
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

// Load dataset for contextual grounding
let dataset = [];
try {
  const data = fs.readFileSync("train/merged_mira.json", "utf-8");
  dataset = JSON.parse(data);
  console.log(`🧠 Loaded ${dataset.length} examples for contextual grounding`);
} catch (err) {
  console.log("⚠️ Dataset not found or unreadable:", err.message);
}

// ---------------- CUSTOM PROMPT ----------------
const SYSTEM_PROMPT = `
You are MIRA — a friendly and empathetic mental health companion.

💡 Your Goals:
- Listen actively to the user's emotions.
- Respond with compassion, clarity, and psychological safety.
- Offer coping strategies, motivation, and mindfulness.
- Never give medical diagnosis; instead encourage professional help when serious.

💬 Tone: Warm, encouraging, and understanding.

Use insights from the provided dataset (examples of supportive dialogue) if relevant.
`;
// ------------------------------------------------

// POST /api/chat
router.post("/", async (req, res) => {
  try {
    const { message } = req.body;

    if (!message) {
      return res.status(400).json({ error: "Message is required." });
    }

    // ✅ Use the working Gemini 2.0 Flash model
    const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash-exp" });

    // Add relevant examples for contextual support
    const fewShotExamples = dataset
      .slice(0, 5)
      .map((ex) => `User: ${ex.instruction}\nMira: ${ex.response}`)
      .join("\n\n");

    const prompt = `
${SYSTEM_PROMPT}

Here are a few example conversations for reference:
${fewShotExamples}

Now continue this new conversation:
User: ${message}
Mira:
`;

    const result = await model.generateContent(prompt);
    const reply = result.response.text();

    res.json({ reply });
  } catch (error) {
    console.error("Error in chat route:", error);
    res.status(500).json({ error: "Failed to generate response" });
  }
});

export default router;