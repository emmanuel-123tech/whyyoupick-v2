import os
import re
import json
import base64
import hashlib
import secrets
import pandas as pd
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Password hashing (pure stdlib — no native compilation needed on Vercel) ───
def hash_password(plain: str) -> str:
    """PBKDF2-SHA256 password hashing using stdlib only."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
    return "pbkdf2:{}:{}".format(salt, base64.b64encode(dk).decode())

def verify_password(plain: str, hashed: str) -> bool:
    """Verify against pbkdf2 hash OR legacy plain-text (migration support)."""
    if hashed.startswith("pbkdf2:"):
        try:
            _, salt, stored_b64 = hashed.split(":", 2)
            dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
            return base64.b64encode(dk).decode() == stored_b64
        except Exception:
            return False
    # Legacy plain-text fallback for accounts created before hashing was added
    return plain == hashed

# ── MongoDB Atlas ─────────────────────────────────────────────────────────────
USE_MONGO = False
_users_col = None

try:
    from pymongo import MongoClient
    MONGO_URI = os.getenv("MONGODB_URI", "")
    if MONGO_URI:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _mongo_db = _mongo_client[os.getenv("MONGODB_DB", "whyyoupick")]
        _users_col = _mongo_db["users"]
        _users_col.create_index("email", unique=True)
        USE_MONGO = True
        print("[OK] MongoDB Atlas connected.")
    else:
        print("[INFO] MONGODB_URI not set - falling back to local file storage.")
except Exception as _mongo_err:
    USE_MONGO = False
    print("[WARN] MongoDB unavailable: {} - falling back to local file storage.".format(_mongo_err))

# Absolute path of this file's directory — required for Vercel serverless
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── File-based fallback ───────────────────────────────────────────────────────
USERS_FILE = "/tmp/users.json" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "users.json")

app = FastAPI(title="WhyYouPick API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Groq AI Client ────────────────────────────────────────────────────────────
_raw_key = os.getenv("GROQ_API_KEY", "").strip()
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=_raw_key
) if _raw_key and _raw_key != "your_groq_api_key_here" else None

if client:
    print("[OK] Groq AI client initialized.")
else:
    print("[WARN] Groq API key missing or invalid - AI features will use fallback responses.")

# ── Load Dataset Sheets ───────────────────────────────────────────────────────
DATASET_PATH = os.path.join(BASE_DIR, "whyyoupick_synthetic_dataset.xlsx")
dataset_loaded = False
df_users = pd.DataFrame()
df_items = pd.DataFrame()
df_reviews = pd.DataFrame()
df_sim = pd.DataFrame()

try:
    df_users  = pd.read_excel(DATASET_PATH, sheet_name="Users")
    df_items  = pd.read_excel(DATASET_PATH, sheet_name="Items")
    df_reviews = pd.read_excel(DATASET_PATH, sheet_name="Reviews_Train")
    df_sim    = pd.read_excel(DATASET_PATH, sheet_name="Simulation_Test")
    dataset_loaded = True
    print("[OK] Dataset loaded - {} items, {} reviews, {} users.".format(
        len(df_items), len(df_reviews), len(df_users)
    ))
except Exception as e:
    print("[WARN] Could not load dataset: {}".format(e))

# ── Category keyword map for query detection ──────────────────────────────────
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Movies":        ["movie", "film", "cinema", "thriller", "action", "comedy", "drama", "watch", "series", "show"],
    "Food":          ["food", "eat", "snack", "drink", "restaurant", "meal", "dish", "cuisine", "burger", "pizza", "rice", "jollof"],
    "Electronics":   ["phone", "laptop", "gadget", "electronic", "device", "computer", "headphone", "speaker", "camera", "tv"],
    "Fashion":       ["cloth", "fashion", "wear", "bag", "shoe", "dress", "outfit", "style", "accessory", "backpack"],
    "Books":         ["book", "read", "novel", "guide", "textbook", "literature", "author", "study", "story"],
    "Places":        ["place", "visit", "travel", "hotel", "location", "spot", "destination", "trip"],
    "Home Tools":    ["home", "tool", "kitchen", "furniture", "appliance", "cleaning", "decor", "household"],
    "School Supplies": ["school", "supply", "pen", "pencil", "notebook", "stationery", "study"],
}

def detect_category(message: str) -> Optional[str]:
    msg_lower = message.lower()
    best_cat, best_hits = None, 0
    for cat, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in msg_lower)
        if hits > best_hits:
            best_hits, best_cat = hits, cat
    return best_cat if best_hits > 0 else None

def get_catalog_items(category: Optional[str], n: int = 12) -> List[dict]:
    if df_items.empty:
        return []
    pool = df_items if not category else df_items[df_items["category"] == category]
    if pool.empty:
        pool = df_items
    sample = pool.sample(min(n, len(pool)), random_state=42)
    return sample[["item_id", "title", "category", "price_level", "description",
                    "strengths", "weaknesses", "base_quality_score", "popularity_score"]].to_dict(orient="records")

def get_dataset_user_profile(user_id: str) -> Optional[dict]:
    if df_users.empty:
        return None
    mask = df_users["user_id"].astype(str).str.upper() == user_id.upper()
    if not mask.any():
        return None
    return df_users[mask].iloc[0].to_dict()

def get_user_reviews(user_id: str, n: int = 20) -> List[dict]:
    if df_reviews.empty:
        return []
    mask = df_reviews["user_id"].astype(str).str.upper() == user_id.upper()
    rows = df_reviews[mask].head(n)
    return rows[["item_id", "rating", "review_text", "sentiment", "tone_label"]].to_dict(orient="records")

# ── Request Models ────────────────────────────────────────────────────────────
class ExtractRequest(BaseModel):
    user_id: str

class SimulateRequest(BaseModel):
    user_id: str
    item_id: str
    item_description: str = ""
    custom_persona: str = ""

class RecommendRequest(BaseModel):
    user_id: str
    message: str
    custom_persona: str = ""

class AuthRequest(BaseModel):
    email: str
    password: str
    name: str = ""

class PreferenceRequest(BaseModel):
    email: str
    reviewer_type: str
    strictness: str
    dealbreaker: str
    shopping_category: str
    explanation_length: str

# ── In-memory + file fallback ─────────────────────────────────────────────────
users_db: dict = {}
if not USE_MONGO and os.path.exists(USERS_FILE):
    try:
        with open(USERS_FILE, "r") as f:
            users_db = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print("[WARN] Could not load users file: {}".format(e))

def save_users():
    if USE_MONGO:
        return
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(users_db, f)
    except Exception as e:
        print("[WARN] Could not save users file: {}".format(e))

# ── MongoDB helpers ───────────────────────────────────────────────────────────
def mongo_get_user(email: str) -> Optional[dict]:
    if not USE_MONGO or _users_col is None:
        return None
    return _users_col.find_one({"email": email}, {"_id": 0})

def mongo_upsert_user(email: str, data: dict):
    if not USE_MONGO or _users_col is None:
        return
    _users_col.update_one({"email": email}, {"$set": {**data, "email": email}}, upsert=True)

# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/api/signup")
def signup(req: AuthRequest):
    if USE_MONGO:
        if mongo_get_user(req.email):
            raise HTTPException(status_code=400, detail="User already exists")
        user_count = _users_col.count_documents({})
        new_user = {"name": req.name, "password": hash_password(req.password), "id": "User_{}".format(user_count + 1)}
        mongo_upsert_user(req.email, new_user)
        return {"message": "Signup successful", "user_id": new_user["id"], "name": req.name}
    else:
        if req.email in users_db:
            raise HTTPException(status_code=400, detail="User already exists")
        users_db[req.email] = {"name": req.name, "password": hash_password(req.password), "id": "User_{}".format(len(users_db) + 1)}
        save_users()
        return {"message": "Signup successful", "user_id": users_db[req.email]["id"], "name": req.name}

@app.post("/api/login")
def login(req: AuthRequest):
    if USE_MONGO:
        user = mongo_get_user(req.email)
        if not user or not verify_password(req.password, user["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"message": "Login successful", "user_id": user["id"], "email": req.email, "name": user["name"]}
    else:
        if req.email not in users_db:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        stored = users_db[req.email]
        if not verify_password(req.password, stored["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"message": "Login successful", "user_id": stored["id"], "email": req.email, "name": stored["name"]}

@app.post("/api/save_preferences")
def save_preferences(req: PreferenceRequest):
    prefs = {
        "reviewer_type": req.reviewer_type,
        "strictness": req.strictness,
        "dealbreaker": req.dealbreaker,
        "shopping_category": req.shopping_category,
        "explanation_length": req.explanation_length,
    }
    if USE_MONGO:
        user = mongo_get_user(req.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        mongo_upsert_user(req.email, {**user, "preferences": prefs})
    else:
        if req.email not in users_db:
            raise HTTPException(status_code=404, detail="User not found")
        users_db[req.email]["preferences"] = prefs
        save_users()
    return {"message": "Preferences saved"}

@app.get("/api/status")
def get_status():
    return {
        "dataset_loaded": dataset_loaded,
        "items": len(df_items),
        "reviews": len(df_reviews),
        "users": len(df_users),
        "ai_connected": client is not None,
        "storage": "MongoDB" if USE_MONGO else "Local File",
    }

# ── User preference string builder ───────────────────────────────────────────
def get_user_preferences(user_id: str) -> str:
    parts = []

    # 1. Saved app preferences
    saved_prefs = None
    if USE_MONGO and _users_col is not None:
        try:
            doc = _users_col.find_one({"id": user_id}, {"_id": 0})
            if doc and "preferences" in doc:
                saved_prefs = doc["preferences"]
        except Exception as e:
            print("[WARN] MongoDB preference lookup: {}".format(e))
    else:
        for u in users_db.values():
            if u.get("id") == user_id and "preferences" in u:
                saved_prefs = u["preferences"]
                break

    if saved_prefs:
        parts.append(
            "App Profile - Reviewer type: {}. Strictness: {}. Dealbreaker: {}. "
            "Favourite category: {}. Detail preference: {}.".format(
                saved_prefs.get("reviewer_type", "balanced"),
                saved_prefs.get("strictness", "moderate"),
                saved_prefs.get("dealbreaker", "none"),
                saved_prefs.get("shopping_category", "general"),
                saved_prefs.get("explanation_length", "medium"),
            )
        )

    # 2. Dataset profile
    ds_profile = get_dataset_user_profile(user_id)
    if ds_profile:
        parts.append(
            "Dataset Profile - Persona: {}. Language mix: {}. Review tone: {}. "
            "Rating strictness: {}. Avg rating tendency: {}. "
            "Likes: {}. Dislikes: {}. Preferred categories: {}.".format(
                ds_profile.get("persona", "general"),
                ds_profile.get("primary_language_mix", "english"),
                ds_profile.get("review_tone", "balanced"),
                ds_profile.get("rating_strictness", "moderate"),
                ds_profile.get("avg_rating_tendency", 3.5),
                ds_profile.get("likes", "N/A"),
                ds_profile.get("dislikes", "N/A"),
                ds_profile.get("preferred_categories", "general"),
            )
        )

    return "\n".join(parts) if parts else "None"

# ── Task A: Extract Signals ───────────────────────────────────────────────────
@app.post("/api/extract_signals")
def extract_signals(req: ExtractRequest):
    ds_profile = get_dataset_user_profile(req.user_id)
    user_reviews = get_user_reviews(req.user_id)

    if not user_reviews and not df_reviews.empty:
        num_part = re.sub(r"[^0-9]", "", req.user_id)
        if num_part:
            mask = df_reviews["user_id"].astype(str).str.contains(num_part, na=False)
            rows = df_reviews[mask].head(20)
            user_reviews = rows[["item_id", "rating", "review_text", "sentiment", "tone_label"]].to_dict(orient="records")

    if client and (user_reviews or ds_profile):
        try:
            review_sample = "\n".join(
                "- [{}/5 | {} | {}] {}".format(
                    r.get("rating", "-"), r.get("sentiment", ""), r.get("tone_label", ""), r.get("review_text", "")
                )
                for r in user_reviews[:15]
            )
            profile_text = ""
            if ds_profile:
                profile_text = (
                    "persona={}, tone={}, strictness={}, avg_rating={}, "
                    "likes={}, dislikes={}, preferred_categories={}".format(
                        ds_profile.get("persona"), ds_profile.get("review_tone"),
                        ds_profile.get("rating_strictness"), ds_profile.get("avg_rating_tendency"),
                        ds_profile.get("likes"), ds_profile.get("dislikes"),
                        ds_profile.get("preferred_categories"),
                    )
                )

            avg_rating = None
            if user_reviews:
                avg_rating = round(sum(r.get("rating", 0) for r in user_reviews) / len(user_reviews), 2)
            if ds_profile and ds_profile.get("avg_rating_tendency") and avg_rating is None:
                avg_rating = float(ds_profile["avg_rating_tendency"])

            profile_line  = "Profile: {}".format(profile_text) if profile_text else ""
            reviews_line  = "Recent reviews:\n{}".format(review_sample) if review_sample else "No reviews available."

            prompt = (
                "Analyse user {}'s behaviour from their profile and reviews.\n\n"
                "{}\n{}\n\n"
                "Return a JSON object with:\n"
                "  'signals'    (array of 6 concise behavioural signal strings),\n"
                "  'avg_rating' (float - computed average rating or {}),\n"
                "  'tone'       (one word describing their writing style),\n"
                "  'biases'     (array of up to 3 bias strings e.g. 'Negative Bias: Battery Life')."
            ).format(req.user_id, profile_line, reviews_line, avg_rating)

            resp = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": "You are a user-behaviour analysis AI. Always output valid JSON only."},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            if avg_rating is not None and result.get("avg_rating") is None:
                result["avg_rating"] = avg_rating
            return result
        except Exception as e:
            print("[WARN] extract_signals AI error: {}".format(e))

    # Fallback
    return {
        "signals": ["Strict Rater", "Concise Tone", "Negative Bias: Price", "Values Durability",
                    "Positive Bias: Build Quality", "Category Focus: Electronics"],
        "avg_rating": 3.2,
        "tone": "critical",
        "biases": ["Negative Bias: Price", "Negative Bias: Battery Life", "Positive Bias: Durability"],
    }

# ── Task A: Simulate Review ───────────────────────────────────────────────────
@app.post("/api/simulate")
def simulate_review(req: SimulateRequest):
    if client:
        user_prefs = req.custom_persona.strip() if req.custom_persona.strip() else get_user_preferences(req.user_id)

        # Resolve item context from dataset
        item_context = req.item_description.strip()
        if not item_context and not df_items.empty:
            mask = df_items["item_id"].astype(str).str.upper() == req.item_id.upper()
            if mask.any():
                row = df_items[mask].iloc[0]
                item_context = (
                    "{} ({}, {}). Description: {}. Strengths: {}. Weaknesses: {}.".format(
                        row["title"], row["category"], row["price_level"],
                        row["description"], row["strengths"], row["weaknesses"],
                    )
                )
        if not item_context and not df_sim.empty:
            sim_mask = (
                (df_sim["user_id"].astype(str).str.upper() == req.user_id.upper()) &
                (df_sim["item_id"].astype(str).str.upper() == req.item_id.upper())
            )
            if sim_mask.any():
                item_context = df_sim[sim_mask].iloc[0].get("item_context", "")
        if not item_context:
            item_context = req.item_id

        persona_note = (
            "The user has no saved profile - simulate a generic Nigerian reviewer."
            if user_prefs == "None"
            else "CRITICAL: Ground every aspect of the review in this user profile:\n{}".format(user_prefs)
        )

        prompt = (
            "You are a review simulation AI (Task A - WhyYouPick Competition).\n"
            "{}\n\n"
            "Product to review: '{}'\n\n"
            "Rules:\n"
            "- Mirror their tone, language mix (English/Pidgin/Igbo/Hausa as per profile), and strictness\n"
            "- Let their likes/dislikes directly influence what they praise or criticise\n"
            "- The rating MUST align with their avg_rating_tendency and strictness level\n"
            "- If the product has weaknesses matching their dislikes, penalise heavily\n\n"
            "Return ONLY valid JSON with keys:\n"
            "  'rating'     (float 1.0-5.0),\n"
            "  'review'     (string - 2-4 sentences in the user's authentic tone),\n"
            "  'confidence' (string like '91%'),\n"
            "  'reasoning'  (array of 3-4 strings explaining how persona traits shaped the prediction)."
        ).format(persona_note, item_context)

        try:
            response = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": "You are a review simulation AI. Always output valid JSON only."},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print("[WARN] AI Error (simulate): {}".format(e))

    return {
        "rating": 3.4,
        "review": "The features are actually pretty good, but for this price tag I expected much better battery life. It feels well built though.",
        "confidence": "92%",
        "reasoning": [
            "Tone Match: Concise and slightly critical.",
            "Preference Hit: 'Well built' aligns with user's value of durability.",
            "Bias Hit: User penalises items heavily for battery/price issues.",
        ],
    }

# ── Task B: Recommend Items ───────────────────────────────────────────────────
@app.post("/api/recommend")
def recommend_items(req: RecommendRequest):
    if client:
        user_prefs = req.custom_persona.strip() if req.custom_persona.strip() else get_user_preferences(req.user_id)

        detected_cat = detect_category(req.message)
        catalog_items = get_catalog_items(detected_cat, n=12)

        persona_note = (
            "The user has no saved profile - make sensible general recommendations."
            if user_prefs == "None"
            else "CRITICAL: Personalise every recommendation based on this user profile:\n{}".format(user_prefs)
        )

        catalog_text = "\n".join(
            "[{}] {} ({}, {}) - {} | Strengths: {} | Weaknesses: {} | Quality: {:.2f} | Popularity: {:.2f}".format(
                it["item_id"], it["title"], it["category"], it["price_level"],
                it["description"], it["strengths"], it["weaknesses"],
                it["base_quality_score"], it["popularity_score"],
            )
            for it in catalog_items
        ) if catalog_items else "(No catalog available - suggest realistic general items.)"

        prompt = (
            "You are a personalised recommendation AI (Task B - WhyYouPick Competition).\n"
            "{}\n\n"
            "Available catalog items (select ONLY from these, do not invent items):\n{}\n\n"
            "User request: '{}'\n\n"
            "Select the 3 BEST items from the catalog that match BOTH the user's request AND their persona.\n"
            "For each item:\n"
            "- Explain exactly WHY it suits their specific likes, dislikes, strictness, and preferred categories\n"
            "- Penalise items whose weaknesses match their known dislikes\n"
            "- Compute a match score (0-100%) based on how well strengths align with their likes\n"
            "- Use a warm, conversational Nigerian tone in response_text\n\n"
            "Return ONLY valid JSON with:\n"
            "  'response_text' (string - 2-3 sentence conversational intro referencing the user's persona),\n"
            "  'items' (array of exactly 3 objects, each with: 'name', 'item_id', 'score' (like '87%'),\n"
            "           'reason' (2 sentences linking item to persona), 'category', 'image_keyword')."
        ).format(persona_note, catalog_text, req.message)

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a personalized recommendation AI. Always output valid JSON only."},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)

            # Enrich items with catalog metadata
            catalog_map = {it["item_id"]: it for it in catalog_items}
            for rec_item in result.get("items", []):
                iid = rec_item.get("item_id", "")
                if iid in catalog_map:
                    ci = catalog_map[iid]
                    rec_item.setdefault("category",      ci["category"])
                    rec_item.setdefault("price_level",   ci["price_level"])
                    rec_item.setdefault("quality_score", ci["base_quality_score"])
            return result
        except Exception as e:
            print("[WARN] AI Error (recommend): {}".format(e))

    return {
        "response_text": "Based on your preference for durability and value, here are my top picks:",
        "items": [
            {"name": "Dell UltraSharp 27\"", "item_id": "I0001", "score": "89%",
             "reason": "Highly durable display with great value for a discerning buyer.", "category": "Electronics", "image_keyword": "monitor"},
            {"name": "LG 27UN850-W",         "item_id": "I0002", "score": "82%",
             "reason": "Great ergonomics and colour accuracy for long work sessions.",   "category": "Electronics", "image_keyword": "monitor"},
            {"name": "BenQ EW2480",           "item_id": "I0003", "score": "78%",
             "reason": "Budget-friendly with solid build quality.",                     "category": "Electronics", "image_keyword": "monitor"},
        ],
    }

# ── Static file serving ───────────────────────────────────────────────────────
@app.get("/")
def serve_landing():
    return FileResponse(os.path.join(BASE_DIR, "landing.html"))

@app.get("/app")
def serve_app():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("Starting WhyYouPick API server on http://localhost:8003...")
    uvicorn.run(app, host="0.0.0.0", port=8003, reload=True)
