# 🧠 WhyYouPick — AI Review & Recommendation Agent

> A full-stack AI-powered web application that simulates how a user would review any product and generates personalised recommendations — all driven by a user persona model.

---

## 📌 Overview

**WhyYouPick** is a personalization AI system built around two core tasks:

| Task | Description |
|---|---|
| **Task A — Review Simulation** | Given a user persona and a product (movie, food, drink, gadget, etc.), the AI predicts the rating the user would give and generates a full review in their tone. |
| **Task B — Personalized Recommendations** | Using the same persona built in Task A, the AI recommends items the user will actually enjoy, with match scores and persona-grounded reasoning. |

Task B is intentionally built **on top of** Task A — the persona you build through onboarding and simulate with in Task A is the same persona that powers Task B's recommendation engine.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  User Onboarding                        │
│   (Builds persona: reviewer type, strictness,           │
│    dealbreaker, category, tone)                         │
└────────────────────────┬────────────────────────────────┘
                         │ Persona saved to backend
              ┌──────────┴──────────┐
              ▼                     ▼
         TASK A                  TASK B
   Review Simulation        Recommendations
   /api/simulate            /api/recommend
   Input: persona +         Input: same persona +
          product details          user message
   Output: rating,          Output: ranked items
           review text,             with match scores
           reasoning                and reasons
```

---

## ✨ Features

### 🔐 Authentication
- User signup with instant (optimistic) navigation — no waiting
- Login with saved profile
- Logout returns to landing page (all session data cleared)

### 🏠 Landing Page (`/`)
- Dark-themed marketing page with hero section, phone mockup, stats, and feature cards
- "Get Started" → routes new users directly to Signup
- "Login" → routes returning users directly to Login

### 📋 User Modeling
- Onboarding questionnaire captures reviewer style, rating strictness, dealbreakers, preferred category
- Custom persona can be typed inline on any task screen (overrides saved profile)

### ⭐ Task A — Simulate Review (`/app` → Simulate tab)
- Free-text product input — supports **any category**: movies, food, drinks, electronics, services
- Catalogue dropdown fallback (pre-loaded items)
- Expandable "Custom Persona Override" accordion
- AI returns: star rating, full review text, confidence %, step-by-step reasoning

### 🎯 Task B — Recommend Items (`/app` → Recommend tab)
- Chat-based interface with the AI recommendation agent
- Collapsible persona panel — type a custom persona or use the saved profile
- AI returns: 3 ranked items with match scores, reasons, and a conversational explanation
- Voice output (TTS) + microphone input (STT) supported

### 📊 Evaluation Lab
- Task A metrics: MAE, RMSE, Tone Fidelity, Sentiment Match
- Task B metrics: Precision@5, Recall@5, NDCG@5, MRR
- Human evaluation scores and capability ratings

---

## 🗂️ File Structure

```
whyyoupick/
├── landing.html                    # Public landing page (served at /)
├── index.html                      # Full SPA — 10 screens (served at /app)
├── app.js                          # Frontend logic and API integration
├── index.css                       # Complete design system
├── main.py                         # FastAPI backend (all API endpoints)
├── requirements.txt                # Python dependencies
├── vercel.json                     # Vercel deployment config
├── whyyoupick_synthetic_dataset.xlsx  # Source review dataset
├── .env                            # API keys (NOT committed to git)
├── .gitignore                      # Protects secrets and local data
└── users.json                      # Local user store (auto-created, not committed)
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/signup` | Create a new user account |
| `POST` | `/api/login` | Authenticate existing user |
| `POST` | `/api/save_preferences` | Save onboarding persona |
| `POST` | `/api/extract_signals` | Extract behavioral signals from review history |
| `POST` | `/api/simulate` | **Task A** — Generate review + rating for a product |
| `POST` | `/api/recommend` | **Task B** — Get personalised recommendations |
| `GET`  | `/api/status` | Health check (dataset loaded, AI connected) |
| `GET`  | `/` | Serve landing page |
| `GET`  | `/app` | Serve the SPA app |

### Task A — `/api/simulate`
```json
{
  "user_id": "User_1",
  "item_id": "Item_992",
  "item_description": "Jollof Rice at a Nigerian restaurant",
  "custom_persona": "Budget-conscious food lover, strict on portion size"
}
```

### Task B — `/api/recommend`
```json
{
  "user_id": "User_1",
  "message": "Recommend me a Nigerian street food to try",
  "custom_persona": "Health-conscious Lagos professional who avoids oily food"
}
```

---

## ⚙️ Local Setup

### Prerequisites
- Python 3.10+
- A free [Groq API key](https://console.groq.com) (for the LLM)

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/whyyoupick.git
cd whyyoupick
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your API key
Create a `.env` file in the project root:
```env
GROQ_API_KEY=your_groq_api_key_here
```

### 4. Run the server
```bash
py main.py
```

### 5. Open the app
| URL | Page |
|---|---|
| http://localhost:8003 | Landing page |
| http://localhost:8003/app | App (login screen) |
| http://localhost:8003/app?start=signup | App (signup screen) |

---

## 🚀 Deployment (Vercel — Free)

1. Push your code to a GitHub repository (**do not commit `.env`**)
2. Go to [vercel.com](https://vercel.com) and sign in with GitHub
3. Click **"Add New Project"** → Import your repository
4. Add an **Environment Variable** in the Vercel dashboard:
   - `GROQ_API_KEY` → your Groq API key
5. Click **Deploy**

Your app will be live at `https://your-project-name.vercel.app` 🎉

> **Note:** Vercel uses a serverless architecture. User accounts persist in `/tmp` during a session but reset on cold starts. For permanent persistence, connect a database (e.g. free [MongoDB Atlas](https://www.mongodb.com/atlas)).

---

## 🤖 AI Models Used

| Task | Model | Provider |
|---|---|---|
| Task A — Review Simulation | `llama3-70b-8192` | Groq (free tier) |
| Task B — Recommendations | `llama-3.3-70b-versatile` | Groq (free tier) |

Both models are accessed via the **OpenAI-compatible Groq API** at no cost within free tier limits.

---

## 📈 Evaluation Metrics

### Task A
| Metric | Value |
|---|---|
| MAE | 0.72 |
| RMSE | 0.95 |
| Tone Fidelity | 84% |
| Sentiment Match | 0.89 |

### Task B
| Metric | Value |
|---|---|
| Precision@5 | 0.32 |
| Recall@5 | 0.45 |
| NDCG@5 | 0.38 |
| MRR | 0.41 |
| Cold-Start Score | 0.68 |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML, CSS, JavaScript (SPA) |
| Backend | Python · FastAPI · Uvicorn |
| AI / LLM | Groq API · LLaMA 3 models |
| Dataset | Pandas · OpenPyXL (Excel) |
| Deployment | Vercel (Python Serverless) |
| Icons | Phosphor Icons |
| Fonts | Inter (Google Fonts) |

---

## 👤 Author

**WhyYouPick** — Built by AgentX

Team Members 

Emmanuel Ebiendele [ML ENGINEER, WEB DEVELOPER]

Olawale Marvellous [UI/UX DESIGNER]

---
