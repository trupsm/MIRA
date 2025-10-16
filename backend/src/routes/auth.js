const express = require('express');
const router = express.Router();
const supabase = require('../config/supabase');

// 🔹 Register
router.post('/register', async (req, res) => {
  const { name, email, password } = req.body;
  if (!name || !email || !password)
    return res.status(400).json({ message: 'All fields required' });

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { name } },
  });

  if (error) return res.status(400).json({ message: error.message });
  res.status(201).json({ message: 'Registration successful', user: data.user });
});

// 🔹 Login
router.post('/login', async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password)
    return res.status(400).json({ message: 'All fields required' });

  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return res.status(400).json({ message: error.message });

  res.json({
    message: 'Login successful',
    token: data.session.access_token,
    user: data.user,
  });
});

module.exports = router;
