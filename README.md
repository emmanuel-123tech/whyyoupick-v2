# WhyYouPick - AI Review & Recommendation Agent

WhyYouPick is a full-stack AI app that simulates how a user would review a product, place, food, movie, or experience, then uses that same persona context to generate personalised recommendations.

The app is built with a vanilla HTML/CSS/JavaScript frontend and a FastAPI backend deployed as a Vercel Python serverless function.

## Overview

| Task | Endpoint | What it does |
|---|---|---|
| Task A - Review Simulation | `POST /api/simulate` | Predicts a rating, review text, confidence, and reasoning for a user/product pair. |
| Task B - Recommendations | `POST /api/recommend` | Recommends items or ideas based on the user's message, persona, and optional catalogue context. |

The backend now treats free-form user input as the source of truth:

- In simulation, `item_description` is used first.
- The catalogue item is only a fallback when the user leaves the description blank.
- In recommendations, the catalogue is optional context, not a hard restriction.
- If the user asks for something outside the synthetic catalogue, the agent can use general knowledge and return `source: "general"`.

## Features

- Signup, login, logout, and onboarding preference capture
- User persona/profile modelling from onboarding and dataset context
- Free-text review simulation for any category
- Optional catalogue fallback for simulation
- Chat-based recommendation agent
- Custom persona override on simulate and recommend screens
- Voice output and microphone input in supported browsers
- Dataset-backed user, item, review, and simulation context
- Vercel-ready Python serverless deployment

## File Structure

```text
whyyoupick-v2/
├── app.py                           # Vercel FastAPI entrypoint and deployed route overrides
├── main.py                          # Main FastAPI app, local server, dataset logic, auth, AI routes
├── index.html                       # Main SPA served at /app
├── landing.html                     # Landing page served at /
├── app.js                           # Frontend logic reference file
├── index.css                        # Frontend CSS reference file
├── requirements.txt                 # Python dependencies
├── vercel.json                      # Vercel deployment config
├── render.yaml                      # Optional Render deployment config
├── whyyoupick_synthetic_dataset.xlsx # Synthetic users/items/reviews dataset
├── .gitignore                       # Protects secrets and local files
└── users.json                       # Local-only user store, generated at runtime
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/signup` | Create a new user account. |
| `POST` | `/api/login` | Authenticate an existing user. |
| `POST` | `/api/save_preferences` | Save onboarding preferences/persona. |
| `POST` | `/api/extract_signals` | Extract behavioural signals from review history. |
| `POST` | `/api/simulate` | Generate a predicted review and rating. |
| `POST` | `/api/recommend` | Generate personalised recommendations. |
| `GET` | `/api/status` | Health check for dataset, AI key presence, and storage mode. |
| `GET` | `/` | Serve the landing page. |
| `GET` | `/app` | Serve the web app. |

### Simulate Request

```json
{
  "user_id": "User_014",
  "item_id": "Item_992",
  "item_description": "A smoky buka jollof rice plate with chicken, plantain, and very spicy pepper sauce",
  "custom_persona": "A Lagos office worker who loves food but dislikes oily meals and is strict about value for money."
}
```

`item_description` is optional, but when provided it takes priority over `item_id`.

### Recommend Request

```json
{
  "user_id": "User_014",
  "message": "I am travelling to Abuja for two days and need a calm affordable place to stay near the city centre",
  "custom_persona": "Budget-conscious professional, dislikes noisy places, values safety and clean rooms."
}
```

The recommendation agent responds to the actual message. It may use catalogue entries when relevant, but it can also make general recommendations outside the dataset.

## Local Setup

### Prerequisites

- Python 3.10+
- A Groq API key from <https://console.groq.com>

### 1. Clone

```bash
git clone https://github.com/emmanuel-123tech/whyyoupick-v2.git
cd whyyoupick-v2
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

`GROQ_MODEL` is optional, but `llama-3.1-8b-instant` is recommended for free-tier Groq projects because it is cheaper and has friendlier limits than the 70B model.

### 4. Run Locally

```bash
py main.py
```

Then open:

| URL | Page |
|---|---|
| `http://localhost:8003` | Landing page |
| `http://localhost:8003/app` | App |
| `http://localhost:8003/api/status` | Backend status |

## Vercel Deployment

This project uses `app.py` as the Vercel Python entrypoint. `app.py` imports the original FastAPI app from `main.py`, then ensures the deployed `/api/simulate` and `/api/recommend` routes prefer free-form input and register before static file serving.

### Environment Variables

Set these in the Vercel dashboard:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

Optional MongoDB persistence:

```env
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB=whyyoupick
```

### Deploy Steps

1. Push changes to GitHub.
2. Import the repository on Vercel.
3. Add the environment variables above.
4. Redeploy after changing any environment variable.
5. Visit `/api/status` to confirm the backend is responding.

### Important Security Note

Never commit or share API keys. If a key is pasted into chat, committed to git, or exposed in logs, rotate it immediately in the Groq dashboard and update Vercel with the new key.

## Groq Models

The backend tries models in this order:

1. `GROQ_MODEL`, if configured
2. `llama-3.3-70b-versatile`
3. `llama-3.1-8b-instant`

For free-tier usage, set:

```env
GROQ_MODEL=llama-3.1-8b-instant
```

Groq model references:

- `llama-3.1-8b-instant`: <https://console.groq.com/docs/model/llama-3.1-8b-instant>
- `llama-3.3-70b-versatile`: <https://console.groq.com/docs/model/llama-3.3-70b-versatile>
- Rate limits: <https://console.groq.com/docs/rate-limits>
- Model permissions: <https://console.groq.com/docs/model-permissions>

## Dataset

The Excel dataset is loaded lazily on first use from:

```text
whyyoupick_synthetic_dataset.xlsx
```

Expected sheets:

- `Users`
- `Items`
- `Reviews_Train`
- `Simulation_Test`

If the dataset cannot load, the API stays online and returns safe fallback responses.

## Persistence Notes

Without MongoDB, Vercel stores user data in `/tmp/users.json`. This is temporary serverless storage and can reset on cold starts. Use MongoDB Atlas or another database for real persistence.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI, Uvicorn |
| AI | Groq OpenAI-compatible API |
| Dataset | Pandas, OpenPyXL, Excel |
| Deployment | Vercel Python Serverless |
| Optional DB | MongoDB Atlas |

## Team

Built by AgentX.

- Emmanuel Ebiendele - ML Engineer, Web Developer
- Olawale Marvellous - UI/UX Designer
