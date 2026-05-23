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

# ── Password hashing (pure stdlib — works on Vercel, no C compilation) ────────
def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
    return "pbkdf2:{}:{}".format(salt, base64.b64encode(dk).decode())

def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("pbkdf2:"):
        try:
            _, salt, stored_b64 = hashed.split(":", 2)
            dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
            return base64.b64encode(dk).decode() == stored_b64
        except Exception:
            return False
    return plain == hashed  # legacy plain-text fallback

# ── MongoDB ───────────────────────────────────────────────────────────────────
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
except Exception as _e:
    USE_MONGO = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = "/tmp/users.json" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "users.json")
DATASET_PATH = os.path.join(BASE_DIR, "whyyoupick_synthetic_dataset.xlsx")

app = FastAPI(title="WhyYouPick API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Groq AI client ────────────────────────────────────────────────────────────
_raw_key = os.getenv("GROQ_API_KEY", "").strip()
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=_raw_key
) if _raw_key and _raw_key not in ("", "your_groq_api_key_here") else None

# ── LAZY dataset loading — loaded once on first use, NOT at import time ───────
_ds: Dict[str, pd.DataFrame] = {}

def _load_dataset() -> Dict[str, pd.DataFrame]:
    global _ds
    if _ds:
        return _ds
    try:
        _ds["users"]   = pd.read_excel(DATASET_PATH, sheet_name="Users")
        _ds["items"]   = pd.read_excel(DATASET_PATH, sheet_name="Items")
        _ds["reviews"] = pd.read_excel(DATASET_PATH, sheet_name="Reviews_Train")
        _ds["sim"]     = pd.read_excel(DATASET_PATH, sheet_name="Simulation_Test")
    except Exception as e:
        print("Dataset load error: {}".format(e))
    return _ds

def _items() -> pd.DataFrame:
    return _load_dataset().get("items", pd.DataFrame())

def _reviews() -> pd.DataFrame:
    return _load_dataset().get("reviews", pd.DataFrame())

def _users_ds() -> pd.DataFrame:
    return _load_dataset().get("users", pd.DataFrame())

def _sim() -> pd.DataFrame:
    return _load_dataset().get("sim", pd.DataFrame())

# ── Category keywords ─────────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "Movies":         ["movie", "film", "cinema", "thriller", "action", "comedy", "drama", "watch", "series", "show"],
    "Food":           ["food", "eat", "snack", "drink", "restaurant", "meal", "dish", "cuisine", "burger", "pizza", "rice", "jollof"],
    "Electronics":    ["phone", "laptop", "gadget", "electronic", "device", "computer", "headphone", "speaker", "camera", "tv"],
    "Fashion":        ["cloth", "fashion", "wear", "bag", "shoe", "dress", "outfit", "style", "accessory", "backpack"],
    "Books":          ["book", "read", "novel", "guide", "textbook", "literature", "author", "study", "story"],
    "Places":         ["place", "visit", "travel", "hotel", "location", "spot", "destination", "trip"],
    "Home Tools":     ["home", "tool", "kitchen", "furniture", "appliance", "cleaning", "decor", "household"],
    "School Supplies":["school", "supply", "pen", "pencil", "notebook", "stationery"],
}

def detect_category(message: str) -> Optional[str]:
    msg = message.lower()
    best_cat, best_hits = None, 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in msg)
        if hits > best_hits:
            best_hits, best_cat = hits, cat
    return best_cat if best_hits > 0 else None

def get_catalog_items(category: Optional[str], n: int = 12) -> List[dict]:
    df = _items()
    if df.empty:
        return []
    pool = df if not category else df[df["category"] == category]
    if pool.empty:
        pool = df
    sample = pool.head(n)   # head() instead of sample() — no numpy randomness needed
    cols = ["item_id", "title", "category", "price_level",
            "description", "strengths", "weaknesses",
            "base_quality_score", "popularity_score"]
    return sample[[c for c in cols if c in sample.columns]].to_dict(orient="records")

def get_dataset_user_profile(user_id: str) -> Optional[dict]:
    df = _users_ds()
    if df.empty:
        return None
    mask = df["user_id"].astype(str).str.upper() == user_id.upper()
    if not mask.any():
        return None
    return df[mask].iloc[0].to_dict()

def get_user_reviews(user_id: str, n: int = 20) -> List[dict]:
    df = _reviews()
    if df.empty:
        return []
    mask = df["user_id"].astype(str).str.upper() == user_id.upper()
    rows = df[mask].head(n)
    cols = ["item_id", "rating", "review_text", "sentiment", "tone_label"]
    return rows[[c for c in cols if c in rows.columns]].to_dict(orient="records")

# ── Request models ────────────────────────────────────────────────────────────
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

# ── File-based user store ─────────────────────────────────────────────────────
users_db: dict = {}
if not USE_MONGO and os.path.exists(USERS_FILE):
    try:
        with open(USERS_FILE, "r") as f:
            users_db = json.load(f)
    except Exception:
        pass

def save_users():
    if USE_MONGO:
        return
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(users_db, f)
    except Exception:
        pass

# ── MongoDB helpers ───────────────────────────────────────────────────────────
def mongo_get_user(email: str) -> Optional[dict]:
    if not USE_MONGO or _users_col is None:
        return None
    return _users_col.find_one({"email": email}, {"_id": 0})

def mongo_upsert_user(email: str, data: dict):
    if not USE_MONGO or _users_col is None:
        return
    _users_col.update_one({"email": email}, {"$set": {**data, "email": email}}, upsert=True)

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/api/signup")
def signup(req: AuthRequest):
    if USE_MONGO:
        if mongo_get_user(req.email):
            raise HTTPException(status_code=400, detail="User already exists")
        uid = "User_{}".format(_users_col.count_documents({}) + 1)
        mongo_upsert_user(req.email, {"name": req.name, "password": hash_password(req.password), "id": uid})
        return {"message": "Signup successful", "user_id": uid, "name": req.name}
    if req.email in users_db:
        raise HTTPException(status_code=400, detail="User already exists")
    uid = "User_{}".format(len(users_db) + 1)
    users_db[req.email] = {"name": req.name, "password": hash_password(req.password), "id": uid}
    save_users()
    return {"message": "Signup successful", "user_id": uid, "name": req.name}

@app.post("/api/login")
def login(req: AuthRequest):
    if USE_MONGO:
        user = mongo_get_user(req.email)
        if not user or not verify_password(req.password, user["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"message": "Login successful", "user_id": user["id"], "email": req.email, "name": user["name"]}
    if req.email not in users_db:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    stored = users_db[req.email]
    if not verify_password(req.password, stored["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful", "user_id": stored["id"], "email": req.email, "name": stored["name"]}

@app.post("/api/save_preferences")
def save_preferences(req: PreferenceRequest):
    prefs = {k: getattr(req, k) for k in
             ["reviewer_type", "strictness", "dealbreaker", "shopping_category", "explanation_length"]}
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
    items = _items()
    reviews = _reviews()
    return {
        "dataset_loaded": not items.empty,
        "items": len(items),
        "reviews": len(reviews),
        "ai_connected": client is not None,
        "storage": "MongoDB" if USE_MONGO else "Local File",
    }

# ── User preference builder ───────────────────────────────────────────────────
def get_user_preferences(user_id: str) -> str:
    parts = []
    saved = None
    if USE_MONGO and _users_col is not None:
        try:
            doc = _users_col.find_one({"id": user_id}, {"_id": 0})
            if doc:
                saved = doc.get("preferences")
        except Exception:
            pass
    else:
        for u in users_db.values():
            if u.get("id") == user_id:
                saved = u.get("preferences")
                break
    if saved:
        parts.append(
            "App Profile - Reviewer type: {}. Strictness: {}. Dealbreaker: {}. "
            "Favourite category: {}. Detail preference: {}.".format(
                saved.get("reviewer_type", "balanced"), saved.get("strictness", "moderate"),
                saved.get("dealbreaker", "none"), saved.get("shopping_category", "general"),
                saved.get("explanation_length", "medium")))
    ds = get_dataset_user_profile(user_id)
    if ds:
        parts.append(
            "Dataset Profile - Persona: {}. Language mix: {}. Tone: {}. "
            "Strictness: {}. Avg rating: {}. Likes: {}. Dislikes: {}. Categories: {}.".format(
                ds.get("persona", "general"), ds.get("primary_language_mix", "english"),
                ds.get("review_tone", "balanced"), ds.get("rating_strictness", "moderate"),
                ds.get("avg_rating_tendency", 3.5), ds.get("likes", "N/A"),
                ds.get("dislikes", "N/A"), ds.get("preferred_categories", "general")))
    return "\n".join(parts) if parts else "None"

# ── Task A: Extract Signals ───────────────────────────────────────────────────
@app.post("/api/extract_signals")
def extract_signals(req: ExtractRequest):
    ds_profile = get_dataset_user_profile(req.user_id)
    user_reviews = get_user_reviews(req.user_id)

    if not user_reviews:
        df = _reviews()
        if not df.empty:
            num = re.sub(r"[^0-9]", "", req.user_id)
            if num:
                rows = df[df["user_id"].astype(str).str.contains(num, na=False)].head(20)
                user_reviews = rows[["item_id", "rating", "review_text"]].to_dict(orient="records")

    if client and (user_reviews or ds_profile):
        try:
            review_sample = "\n".join(
                "- [{}/5] {}".format(r.get("rating", "-"), r.get("review_text", ""))
                for r in user_reviews[:15])
            profile_text = ""
            if ds_profile:
                profile_text = "persona={}, tone={}, strictness={}, avg={}, likes={}, dislikes={}".format(
                    ds_profile.get("persona"), ds_profile.get("review_tone"),
                    ds_profile.get("rating_strictness"), ds_profile.get("avg_rating_tendency"),
                    ds_profile.get("likes"), ds_profile.get("dislikes"))
            avg = None
            if user_reviews:
                ratings = [r.get("rating", 0) for r in user_reviews if r.get("rating")]
                avg = round(sum(ratings) / len(ratings), 2) if ratings else None
            if not avg and ds_profile:
                avg = ds_profile.get("avg_rating_tendency")

            prompt = (
                "Analyse user {} reviews.\nProfile: {}\nReviews:\n{}\n\n"
                "Return JSON: signals (6 strings), avg_rating ({}), tone (1 word), biases (3 strings)."
            ).format(req.user_id, profile_text, review_sample, avg)
            resp = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": "Behaviour analysis AI. Output valid JSON only."},
                    {"role": "user", "content": prompt}],
                response_format={"type": "json_object"})
            result = json.loads(resp.choices[0].message.content)
            if avg and not result.get("avg_rating"):
                result["avg_rating"] = avg
            return result
        except Exception as e:
            print("extract_signals error: {}".format(e))

    return {
        "signals": ["Strict Rater", "Concise Tone", "Negative Bias: Price", "Values Durability",
                    "Positive Bias: Build Quality", "Category Focus: Electronics"],
        "avg_rating": 3.2, "tone": "critical",
        "biases": ["Negative Bias: Price", "Negative Bias: Battery Life", "Positive Bias: Durability"]}

# ── Task A: Simulate ──────────────────────────────────────────────────────────
@app.post("/api/simulate")
def simulate_review(req: SimulateRequest):
    if client:
        user_prefs = req.custom_persona.strip() or get_user_preferences(req.user_id)
        item_ctx = req.item_description.strip()
        if not item_ctx:
            df = _items()
            if not df.empty:
                mask = df["item_id"].astype(str).str.upper() == req.item_id.upper()
                if mask.any():
                    r = df[mask].iloc[0]
                    item_ctx = "{} ({}, {}). {}\nStrengths: {}\nWeaknesses: {}".format(
                        r.get("title"), r.get("category"), r.get("price_level"),
                        r.get("description"), r.get("strengths"), r.get("weaknesses"))
        if not item_ctx:
            df = _sim()
            if not df.empty:
                m = (df["user_id"].astype(str).str.upper() == req.user_id.upper()) & \
                    (df["item_id"].astype(str).str.upper() == req.item_id.upper())
                if m.any():
                    item_ctx = str(df[m].iloc[0].get("item_context", req.item_id))
        if not item_ctx:
            item_ctx = req.item_id

        persona_note = ("No saved profile - simulate a generic Nigerian reviewer."
                        if user_prefs == "None"
                        else "IMPORTANT user profile:\n{}".format(user_prefs))
        prompt = (
            "You are a review simulation AI (Task A).\n{}\n\nProduct: '{}'\n\n"
            "Rules: mirror tone/language mix/strictness from profile. "
            "Rating must match avg_rating_tendency. Penalise if product weaknesses match dislikes.\n\n"
            "Return JSON: rating (float 1-5), review (2-4 sentences), "
            "confidence (string like 91%), reasoning (array of 3-4 strings)."
        ).format(persona_note, item_ctx)
        try:
            resp = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": "Review simulation AI. Output valid JSON only."},
                    {"role": "user", "content": prompt}],
                response_format={"type": "json_object"})
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            print("simulate error: {}".format(e))

    return {
        "rating": 3.4,
        "review": "The features are good but for this price tag I expected better battery life. Solid build quality though.",
        "confidence": "92%",
        "reasoning": ["Tone Match: Concise and critical.", "Preference Hit: Durability valued.",
                      "Bias Hit: Penalised for price/battery."]}

# ── Task B: Recommend ─────────────────────────────────────────────────────────
@app.post("/api/recommend")
def recommend_items(req: RecommendRequest):
    if client:
        user_prefs = req.custom_persona.strip() or get_user_preferences(req.user_id)
        cat = detect_category(req.message)
        catalog = get_catalog_items(cat, n=12)

        persona_note = ("No saved profile - make general recommendations."
                        if user_prefs == "None"
                        else "IMPORTANT user profile:\n{}".format(user_prefs))

        catalog_text = "\n".join(
            "[{}] {} ({}, {}) | {} | Strengths: {} | Weaknesses: {}".format(
                it.get("item_id",""), it.get("title",""), it.get("category",""),
                it.get("price_level",""), it.get("description",""),
                it.get("strengths",""), it.get("weaknesses",""))
            for it in catalog
        ) if catalog else "(Use general knowledge to suggest 3 items)"

        prompt = (
            "You are a personalised recommendation AI (Task B).\n{}\n\n"
            "Catalog (pick ONLY from these):\n{}\n\n"
            "User says: '{}'\n\n"
            "Pick the 3 BEST items matching the user's request AND persona. "
            "Penalise items whose weaknesses match dislikes. "
            "Score 0-100%% based on how strengths match likes.\n\n"
            "Return JSON: response_text (warm 2-3 sentence Nigerian-tone intro), "
            "items (array of 3 objects with: name, item_id, score, reason (2 sentences), "
            "category, image_keyword)."
        ).format(persona_note, catalog_text, req.message)
        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Personalised recommendation AI. Output valid JSON only."},
                    {"role": "user", "content": prompt}],
                response_format={"type": "json_object"})
            result = json.loads(resp.choices[0].message.content)
            # Enrich with catalog metadata
            cmap = {it["item_id"]: it for it in catalog}
            for item in result.get("items", []):
                ci = cmap.get(item.get("item_id", ""), {})
                item.setdefault("category",      ci.get("category", ""))
                item.setdefault("price_level",   ci.get("price_level", ""))
                item.setdefault("quality_score", ci.get("base_quality_score", ""))
            return result
        except Exception as e:
            print("recommend error: {}".format(e))

    return {
        "response_text": "Based on your preference for durability and value, here are my top picks:",
        "items": [
            {"name": "Action Thriller 1", "item_id": "I0001", "score": "89%",
             "reason": "High quality with great value.", "category": "Movies", "image_keyword": "movie"},
            {"name": "Backpack 2",        "item_id": "I0002", "score": "82%",
             "reason": "Durable and practical design.", "category": "Fashion", "image_keyword": "backpack"},
            {"name": "Bible Study Guide 3","item_id": "I0003","score": "78%",
             "reason": "Great quality for the price.", "category": "Books",   "image_keyword": "book"},
        ]}

# ── Static serving ────────────────────────────────────────────────────────────
@app.get("/")
def serve_landing():
    return FileResponse(os.path.join(BASE_DIR, "landing.html"))

@app.get("/app")
def serve_app():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, reload=True)
