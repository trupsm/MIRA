require('dotenv').config();
const express = require('express');
const cors = require('cors');
const authRoutes = require('./routes/auth');
const moodRoute = require('./routes/mood');
const journalRoute = require('./routes/journal');
const chatRoute = require('./routes/chat');

const app = express();
app.use(cors());
app.use(express.json());

app.get('/api/health', (_, res) => res.json({ status: 'ok', time: new Date() }));

app.use('/api/auth', authRoutes);
app.use('/api/mood', moodRoute);
app.use('/api/journal', journalRoute);
app.use('/api/chat', chatRoute);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`🚀 MIRA backend running on ${PORT}`));
