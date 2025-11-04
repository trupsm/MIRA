import dotenv from "dotenv";
import express from "express";
import cors from "cors";

import authRoutes from "./routes/auth.js";
import moodRoute from "./routes/mood.js";
import journalRoute from "./routes/journal.js";
import chatRoute from "./routes/chat.js";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

app.get("/api/health", (_, res) =>
  res.json({ status: "ok", time: new Date() })
);

app.use("/api/auth", authRoutes);
app.use("/api/mood", moodRoute);
app.use("/api/journal", journalRoute);
app.use("/api/chat", chatRoute);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`🚀 MIRA backend running on ${PORT}`));
