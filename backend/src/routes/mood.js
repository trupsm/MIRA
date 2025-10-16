const express = require('express');
const router = express.Router();
const supabase = require('../config/supabase');
const auth = require('../middleware/auth');

// 🔹 Add new mood entry
router.post('/', auth, async (req, res) => {
  const { mood, note } = req.body;

  if (!mood) {
    return res.status(400).json({ message: 'Mood is required' });
  }

  const { data, error } = await supabase
    .from('mood_entries')
    .insert([{ user_id: req.user.id, mood, note }])
    .select();

  if (error) {
    console.error('❌ Insert error:', error.message);
    return res.status(500).json({ message: 'Failed to add mood' });
  }

  res.status(201).json({ message: 'Mood added successfully', mood: data[0] });
});

// 🔹 Get mood history for user
router.get('/', auth, async (req, res) => {
  const { data, error } = await supabase
    .from('mood_entries')
    .select('*')
    .eq('user_id', req.user.id)
    .order('created_at', { ascending: false });

  if (error) {
    console.error('❌ Fetch error:', error.message);
    return res.status(500).json({ message: 'Failed to fetch moods' });
  }

  res.json({ moods: data });
});

module.exports = router;
