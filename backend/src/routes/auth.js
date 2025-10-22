const express = require('express');
const router = express.Router();
const supabase = require('../config/supabase');
require('dotenv').config();

/**
 * 🔹 REGISTER USER + CREATE DEFAULT EMERGENCY CONTACT
 */
router.post('/register', async (req, res) => {
  const { name, email, password, emergency_contact } = req.body;

  if (!name || !email || !password)
    return res.status(400).json({ message: 'Name, email, and password are required.' });

  try {
    // Create Supabase user
    const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { name },
      },
    });

    if (signUpError) return res.status(400).json({ message: signUpError.message });

    const user = signUpData.user;
    if (!user) return res.status(500).json({ message: 'User registration failed.' });

    // Add emergency contact (optional)
    if (emergency_contact && typeof emergency_contact === 'object') {
      const { name: contactName, relationship, phone_number } = emergency_contact;
      if (contactName && phone_number) {
        await supabase.from('emergency_contacts').insert([
          {
            user_id: user.id,
            name: contactName,
            relationship: relationship || 'Not specified',
            phone_number,
            is_primary: true,
            opted_in: true,
            allow_auto_call: false,
          },
        ]);
      }
    }

    res.status(201).json({
      message: 'User registered successfully!',
      user: {
        id: user.id,
        email: user.email,
        name,
      },
    });
  } catch (err) {
    console.error('❌ Registration error:', err);
    res.status(500).json({ message: 'Internal server error', error: err.message });
  }
});

/**
 * 🔹 LOGIN USER
 */
router.post('/login', async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password)
    return res.status(400).json({ message: 'Email and password required.' });

  try {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) return res.status(400).json({ message: error.message });

    res.json({
      message: 'Login successful!',
      token: data.session?.access_token,
      user: data.user,
    });
  } catch (err) {
    console.error('❌ Login error:', err);
    res.status(500).json({ message: 'Login failed', error: err.message });
  }
});

/**
 * 🔹 GET CURRENT USER FROM TOKEN
 */
router.get('/me', async (req, res) => {
  const token = req.headers.authorization?.split(' ')[1];

  if (!token) return res.status(401).json({ message: 'No token provided' });

  try {
    const { data, error } = await supabase.auth.getUser(token);

    if (error) return res.status(401).json({ message: 'Invalid token' });

    res.json({ user: data.user });
  } catch (err) {
    console.error('❌ /me error:', err);
    res.status(500).json({ message: 'Server error', error: err.message });
  }
});

module.exports = router;
