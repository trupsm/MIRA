require('dotenv').config();
const express = require('express');
const cors = require('cors');
const authRoutes = require('./routes/auth');
const meRoute = require('./routes/me');
const moodRoute = require('./routes/mood');
const journalRoute = require('./routes/journal');

const app = express();
app.use(cors());
app.use(express.json());

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', time: new Date().toISOString() });
});

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/me', meRoute);

//mood entries
app.use('/api/mood', moodRoute);

//journal
app.use('/api/journal', journalRoute);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));
