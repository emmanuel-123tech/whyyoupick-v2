# WhyYouPick

**AI-powered review simulation and personalised recommendation system**

WhyYouPick is a production-oriented full-stack AI application that models user preference behaviour, predicts how a user would review an item, and uses that same behavioural profile to generate personalised recommendations across products, food, movies, places, books, electronics, fashion, and other everyday decision categories.

The system combines a FastAPI backend, a mobile-first web experience, a synthetic behavioural dataset, and Groq-hosted LLaMA models accessed through an OpenAI-compatible API. It is designed for lightweight deployment on Vercel while preserving a clear path to persistent storage through MongoDB.

## Product Summary

Modern recommendation systems often suggest popular items without explaining how those suggestions fit a specific user's review style, dislikes, strictness, or decision patterns. WhyYouPick addresses that gap by building a reusable user persona model and applying it to two connected tasks:

| Capability | Description |
|---|---|
| Review Simulation | Predicts the rating, review tone, confidence, and reasoning a user would likely give for a product, place, meal, movie, or experience. |
| Personalised Recommendation | Recommends options based on the user's natural-language request, saved persona, dataset history, and optional catalogue context. |
| Explainable Reasoning | Returns reasoning signals so the user can understand why an output was produced. |
| Free-form Input | Supports natural user descriptions instead of forcing every request into a fixed catalogue. |

## Competition Value Proposition

WhyYouPick is built as a practical AI agent rather than a static demo. The application demonstrates:

- A complete end-to-end user journey: landing page, authentication, onboarding, modelling, simulation, recommendation, and evaluation screens.
- A shared persona layer reused across multiple AI tasks.
- Free-form reasoning over user input with optional dataset grounding.
- Deployment-ready backend architecture for serverless environments.
- Clear failure handling when dataset, API, or persistence services are unavailable.
- Extensible architecture for replacing the synthetic dataset with real user behaviour data.

## Core Workflow

```text
User Onboarding
      |
      v
Persona + Preference Model
      |
      +---------------------------+
      |                           |
      v                           v
Task A: Review Simulation     Task B: Recommendation
/api/simulate                 /api/recommend
      |                           |
      v                           v
Predicted rating, review,     Ranked suggestions,
confidence, reasoning         match scores, reasons
```

Task B builds on the same persona context used in Task A, so recommendations are not generic. They are shaped by user strictness, dealbreakers, preferred categories, tone, historical ratings, and optional custom persona overrides.

## Key Features

### User Modelling

- Onboarding questionnaire for reviewer type, strictness, dealbreakers, category preference, and explanation style.
- Dataset-backed user profiles from the synthetic review dataset.
- Signal extraction from review history.
- Custom persona override for simulation and recommendation tasks.

### Task A - Review Simulation

- Accepts any free-text product or experience description.
- Uses catalogue metadata only when no description is provided.
- Generates rating, simulated review, confidence, interpreted item, and reasoning.
- Avoids static output by grounding the response in the actual typed item.

### Task B - Recommendation Agent

- Chat-based recommendation flow.
- Responds directly to the user's message instead of forcing catalogue-only picks.
- Can recommend from catalogue items or general knowledge.
- Returns ranked items with score, reason, category, image keyword, and source.
- Supports voice output and microphone input in compatible browsers.

### Reliability and Deployment

- FastAPI backend with Vercel-compatible `app.py` entrypoint.
- Lazy dataset loading to reduce serverless cold-start risk.
- Safe fallback responses if Groq or the dataset is unavailable.
- Groq model fallback strategy for free-tier deployments.
- Optional MongoDB persistence for production user storage.

## Architecture

```text
Frontend
HTML / CSS / JavaScript SPA
      |
      | HTTP JSON API
      v
Backend
FastAPI on Vercel Python Serverless
      |
      +--> Dataset Layer
      |    Pandas + OpenPyXL + Excel workbook
      |
      +--> AI Layer
      |    Groq OpenAI-compatible API
      |
      +--> User Storage
           /tmp JSON fallback or MongoDB Atlas
```

## Repository Structure

```text
whyyoupick-v2/
├── app.py                            # Vercel FastAPI entrypoint and deployed route overrides
├── main.py                           # Main FastAPI application, local server, auth, dataset, AI logic
├── index.html                        # Mobile-first application UI served at /app
├── landing.html                      # Public landing page served at /
├── app.js                            # Frontend logic reference file
├── index.css                         # Frontend style reference file
├── requirements.txt                  # Python dependencies
├── vercel.json                       # Vercel build and routing configuration
├── render.yaml                       # Optional Render deployment configuration
├── whyyoupick_synthetic_dataset.xlsx # Synthetic users, items, reviews, and simulation test data
├── .gitignore                        # Excludes secrets and generated local files
└── users.json                        # Local-only generated user store, not committed
```

## Backend API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/signup` | Register a user. |
| `POST` | `/api/login` | Authenticate a user. |
| `POST` | `/api/save_preferences` | Save onboarding preference data. |
| `POST` | `/api/extract_signals` | Extract behavioural signals from review history. |
| `POST` | `/api/simulate` | Run Task A review simulation. |
| `POST` | `/api/recommend` | Run Task B recommendation generation. |
| `GET` | `/api/status` | Return dataset, AI, and storage health information. |
| `GET` | `/` | Serve the landing page. |
| `GET` | `/app` | Serve the main web application. |

### Example: Review Simulation

```json
{
  "user_id": "User_014",
  "item_id": "Item_992",
  "item_description": "A smoky buka jollof rice plate with chicken, plantain, and very spicy pepper sauce",
  "custom_persona": "A Lagos office worker who loves food but dislikes oily meals and is strict about value for money."
}
```

Expected response shape:

```json
{
  "rating": 3.8,
  "review": "The flavour is strong and satisfying, but the pepper level and oiliness may be a bit much for me. I would enjoy it if the portion is fair for the price.",
  "confidence": "86%",
  "reasoning": [
    "Used the typed product description first.",
    "Matched the user's food preference and value sensitivity.",
    "Penalised likely oiliness and high spice level."
  ],
  "used_catalogue": false,
  "interpreted_item": "smoky buka jollof rice plate"
}
```

### Example: Recommendation

```json
{
  "user_id": "User_014",
  "message": "I am travelling to Abuja for two days and need a calm affordable place to stay near the city centre",
  "custom_persona": "Budget-conscious professional, dislikes noisy places, values safety and clean rooms."
}
```

Recommendation responses can include catalogue-backed items or general suggestions:

```json
{
  "response_text": "For a short Abuja stay, I would prioritise a quiet serviced apartment or budget hotel around Wuse 2, Garki, or Maitama edges, depending on your transport plan.",
  "items": [
    {
      "name": "Quiet serviced apartment near Wuse 2",
      "item_id": "",
      "score": "88%",
      "reason": "Strong fit for a budget-conscious traveller who values quiet, safety, and clean rooms.",
      "category": "Places",
      "image_keyword": "serviced apartment Abuja",
      "source": "general"
    }
  ]
}
```

## Dataset

The application uses `whyyoupick_synthetic_dataset.xlsx`, loaded lazily on first dataset access.

Expected workbook sheets:

| Sheet | Purpose |
|---|---|
| `Users` | User personas, tone, rating tendencies, likes, dislikes, and preferred categories. |
| `Items` | Catalogue items, categories, price levels, descriptions, strengths, and weaknesses. |
| `Reviews_Train` | Historical review samples used for behavioural signal extraction. |
| `Simulation_Test` | Test contexts for review simulation evaluation. |

The backend remains available even if dataset loading fails. In that case, endpoints return safe fallback responses instead of crashing.

## AI Model Strategy

WhyYouPick uses Groq's OpenAI-compatible API for LLaMA model inference.

The backend attempts models in this order:

1. `GROQ_MODEL`, if configured
2. `llama-3.3-70b-versatile`
3. `llama-3.1-8b-instant`

For free-tier Groq projects, the recommended setting is:

```env
GROQ_MODEL=llama-3.1-8b-instant
```

This keeps the app responsive under tighter free-tier rate and token limits while still supporting structured reasoning.

Model references:

- `llama-3.1-8b-instant`: <https://console.groq.com/docs/model/llama-3.1-8b-instant>
- `llama-3.3-70b-versatile`: <https://console.groq.com/docs/model/llama-3.3-70b-versatile>
- Rate limits: <https://console.groq.com/docs/rate-limits>
- Model permissions: <https://console.groq.com/docs/model-permissions>

## Local Development

### Requirements

- Python 3.10+
- Groq API key
- Optional MongoDB Atlas cluster for persistent production-style storage

### Setup

```bash
git clone https://github.com/emmanuel-123tech/whyyoupick-v2.git
cd whyyoupick-v2
pip install -r requirements.txt
```

Create `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant

# Optional persistence
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB=whyyoupick
```

Run locally:

```bash
py main.py
```

Local URLs:

| URL | Description |
|---|---|
| `http://localhost:8003` | Landing page |
| `http://localhost:8003/app` | Main app |
| `http://localhost:8003/api/status` | Backend health check |

## Production Deployment

### Vercel

The project is configured for Vercel Python serverless deployment.

`vercel.json` routes all traffic to `app.py`. The `app.py` entrypoint imports the app from `main.py`, patches the deployed AI routes, and ensures API routes are registered before static file serving.

Required Vercel environment variables:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

Recommended production persistence:

```env
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB=whyyoupick
```

Deployment checklist:

1. Push the latest code to GitHub.
2. Import the repository into Vercel.
3. Add environment variables in the Vercel dashboard.
4. Redeploy after any environment variable change.
5. Visit `/api/status` to confirm the backend is running.
6. Test `/api/simulate` with a free-form item description.
7. Test `/api/recommend` with an out-of-catalogue natural-language request.

## Security Notes

- Do not commit `.env`, API keys, MongoDB credentials, or generated user data.
- If an API key is pasted into chat, committed, or exposed in logs, rotate it immediately.
- Store production secrets only in Vercel environment variables or another secret manager.
- `users.json` is for local fallback only and should not be used as durable production storage.

## Persistence Strategy

| Mode | Storage | Suitable for |
|---|---|---|
| Local fallback | `users.json` | Local demos and development only. |
| Vercel fallback | `/tmp/users.json` | Temporary serverless sessions; resets on cold starts. |
| MongoDB | MongoDB Atlas collection | Production-style user persistence. |

For competition demos, MongoDB is recommended if judges will create accounts and return later.

## Evaluation Context

The application includes an Evaluation Lab screen with placeholder metrics for Task A and Task B. These metrics are intended to communicate the evaluation framework:

| Task | Example Metrics |
|---|---|
| Task A - Simulation | MAE, RMSE, tone fidelity, sentiment match, human behavioural fidelity. |
| Task B - Recommendation | Precision@K, Recall@K, NDCG@K, MRR, cold-start handling, cross-domain support. |

Future production evaluation should compute these metrics directly from held-out test data and human review panels.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI, Uvicorn |
| AI Inference | Groq OpenAI-compatible API |
| Models | LLaMA 3.1 / 3.3 family |
| Dataset | Excel, Pandas, OpenPyXL |
| Deployment | Vercel Python Serverless |
| Optional Database | MongoDB Atlas |
| Icons | Phosphor Icons |

## Roadmap

- Replace synthetic data with real user review imports.
- Add admin dataset upload and validation.
- Persist full interaction history in MongoDB.
- Add automated evaluation scripts for Task A and Task B metrics.
- Add observability for model failures, latency, and rate-limit events.
- Expand recommendation sources beyond the local catalogue.

## Team

Built by **AgentX**.

| Name | Role |
|---|---|
| Emmanuel Ebiendele | ML Engineer, Web Developer |
| Olawale Marvellous | UI/UX Designer |
