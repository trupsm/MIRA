import express from "express";
import supabase from "../config/supabase.js";
import bcrypt from "bcryptjs";
import dotenv from "dotenv";
dotenv.config();

const router = express.Router();

/**
 * -------------------------------
 * REGISTER (User + Emergency Contact)
 * -------------------------------
 * Body:
 * {
 *   "name": "Trupthi",
 *   "email": "trupthi@example.com",
 *   "password": "Password123",
 *   "emergency_contact": {
 *       "name": "Mom",
 *       "relationship": "Mother",
 *       "phone_number": "+91XXXXXXXXXX",
 *       "email": "mom@example.com"
 *   }
 * }
 */
router.post("/register", async (req, res) => {
  const { name, email, password, emergency_contact } = req.body;

  if (!name || !email || !password)
    return res
      .status(400)
      .json({ message: "All fields (name, email, password) are required" });

  try {
    // Register the user with Supabase Auth
    const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { name },
      },
    });

    if (signUpError) throw signUpError;
    const user = signUpData.user;

    // Add default emergency contact (if provided)
    if (emergency_contact && user) {
      const { name, relationship, phone_number, email: contact_email } =
        emergency_contact;

      await supabase.from("emergency_contacts").insert([
        {
          user_id: user.id,
          name,
          relationship,
          phone_number,
          email: contact_email,
          is_primary: true,
          opted_in: true,
          allow_auto_call: true,
        },
      ]);
    }

    res.status(201).json({
      message: "User registered successfully",
      user: {
        id: user.id,
        email: user.email,
        name: name,
        emergency_contact_added: !!emergency_contact,
      },
    });
  } catch (err) {
    console.error("Register Error:", err);
    res
      .status(500)
      .json({ message: "Registration failed", error: err.message });
  }
});

/**
 * -------------------------------
 * LOGIN
 * -------------------------------
 * Body: { "email": "...", "password": "..." }
 */
router.post("/login", async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password)
    return res.status(400).json({ message: "Email and password required" });

  try {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) throw error;

    const token = data.session.access_token;
    const user = data.user;

    res.json({
      message: "Login successful",
      token,
      user: {
        id: user.id,
        email: user.email,
        name: user.user_metadata?.name,
      },
    });
  } catch (err) {
    console.error("Login Error:", err);
    res.status(401).json({ message: "Invalid credentials", error: err.message });
  }
});

/**
 * -------------------------------
 * GET CURRENT USER
 * -------------------------------
 * Requires Authorization: Bearer <token>
 */
router.get("/me", async (req, res) => {
  const authHeader = req.headers.authorization;
  if (!authHeader)
    return res.status(401).json({ message: "Authorization token required" });

  const token = authHeader.split(" ")[1];
  try {
    const { data, error } = await supabase.auth.getUser(token);
    if (error) throw error;

    res.json({ user: data.user });
  } catch (err) {
    console.error("Get User Error:", err);
    res
      .status(401)
      .json({ message: "Invalid or expired token", error: err.message });
  }
});

export default router;
