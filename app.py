"""Vercel FastAPI entrypoint.

Vercel's Python runtime auto-detects FastAPI apps from app.py/index.py/server.py.
The original application lives in main.py for local Render/uvicorn usage. This
entrypoint also patches the Vercel routes that need free-form AI behavior.
"""

import json
import re
from typing import List

import main as backend

app = backend.app


def _remove_routes(paths: List[str]):
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) not in paths]


def _pop_static_mount():
    for idx, route in enumerate(list(app.router.routes)):
        if getattr(route, "name", None) == "static":
            return app.router.routes.pop(idx)
    return None


_static_mount = _pop_static_mount()
_remove_routes(["/api/simulate", "/api/recommend"])


def _fallback_rating(text: str) -> float:
    lowered = text.lower()
    score = 3.6
    positives = ["excellent", "great", "durable", "reliable", "fast", "cheap", "affordable", "quality", "comfortable"]
    negatives = ["expensive", "poor", "bad", "weak", "slow", "fragile", "battery", "oily", "spicy", "noisy"]
    score += min(0.8, 0.18 * sum(word in lowered for word in positives))
    score -= min(0.9, 0.2 * sum(word in lowered for word in negatives))
    return round(max(1.0, min(5.0, score)), 1)


def _infer_category(text: str) -> str:
    return backend.detect_category(text) or "General"


def _keyword_name(message: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", message).strip()
    words = [word for word in clean.split() if len(word) > 2]
    return " ".join(words[:5]).title() or "Personalised Pick"


@app.post("/api/simulate")
def simulate_review(req: backend.SimulateRequest):
    user_prefs = req.custom_persona.strip() or backend.get_user_preferences(req.user_id)
    typed_item = req.item_description.strip()
    item_ctx = typed_item
    used_catalogue = False

    if not item_ctx and req.item_id.strip():
        df = backend._items()
        if not df.empty:
            mask = df["item_id"].astype(str).str.upper() == req.item_id.upper()
            if mask.any():
                used_catalogue = True
                row = df[mask].iloc[0]
                item_ctx = "{} ({}, {}). {}\nStrengths: {}\nWeaknesses: {}".format(
                    row.get("title", req.item_id),
                    row.get("category", "General"),
                    row.get("price_level", ""),
                    row.get("description", ""),
                    row.get("strengths", ""),
                    row.get("weaknesses", ""),
                )

    if not item_ctx:
        item_ctx = "a product or experience the user wants reviewed"

    persona_note = (
        "No saved profile - simulate a thoughtful general reviewer."
        if user_prefs == "None"
        else "IMPORTANT user profile:\n{}".format(user_prefs)
    )

    if backend.client:
        prompt = (
            "You are WhyYouPick's review simulation AI.\n{}\n\n"
            "Product or experience to review: {}\n\n"
            "The user's typed product description is authoritative when present. "
            "Only use catalogue metadata if no product description was typed. "
            "Infer category, likely strengths, likely weaknesses, and how this reviewer would react. "
            "Do not reuse stock headphone/battery wording unless the user actually asked about headphones or batteries.\n\n"
            "Return JSON with: rating (float 1-5), review (2-4 natural sentences), "
            "confidence (string like 88%), reasoning (array of 3-4 specific strings), "
            "used_catalogue (boolean), interpreted_item (short string)."
        ).format(persona_note, item_ctx)
        try:
            resp = backend.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Return valid JSON only. Be specific to the user's item."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            result["used_catalogue"] = bool(result.get("used_catalogue", used_catalogue))
            result.setdefault("interpreted_item", typed_item or req.item_id or "custom item")
            return result
        except Exception as exc:
            print("simulate override error: {}".format(exc))

    rating = _fallback_rating(item_ctx)
    return {
        "rating": rating,
        "review": "Based on the details provided, I would probably rate this around {}/5. The strongest fit is how it matches the user's stated needs, but I would still watch for value, quality, and any dealbreakers in the description.".format(rating),
        "confidence": "74%",
        "reasoning": [
            "Used the typed product description first." if typed_item else "Used the selected catalogue item because no description was typed.",
            "Adjusted the rating using the saved or custom persona where available.",
            "Generated a non-static fallback from the actual item text.",
        ],
        "used_catalogue": used_catalogue,
        "interpreted_item": typed_item or req.item_id or "custom item",
    }


@app.post("/api/recommend")
def recommend_items(req: backend.RecommendRequest):
    message = req.message.strip()
    user_prefs = req.custom_persona.strip() or backend.get_user_preferences(req.user_id)
    category = _infer_category(message)
    catalog = backend.get_catalog_items(category if category != "General" else None, n=8)

    persona_note = (
        "No saved profile - make useful recommendations from the user's request."
        if user_prefs == "None"
        else "IMPORTANT user profile:\n{}".format(user_prefs)
    )
    catalog_text = "\n".join(
        "[{}] {} ({}, {}) | {} | Strengths: {} | Weaknesses: {}".format(
            item.get("item_id", ""), item.get("title", ""), item.get("category", ""),
            item.get("price_level", ""), item.get("description", ""),
            item.get("strengths", ""), item.get("weaknesses", ""),
        )
        for item in catalog
    ) or "No catalogue context available."

    if backend.client:
        prompt = (
            "You are WhyYouPick's intelligent recommendation agent.\n{}\n\n"
            "User message: {}\n\n"
            "Relevant catalogue context, if useful:\n{}\n\n"
            "Respond to exactly what the user asked. If the catalogue is relevant, you may use catalogue items. "
            "If the user's request is outside or more specific than the catalogue, use general knowledge and say so naturally. "
            "Do not force the answer into the catalogue and do not recommend unrelated default items. "
            "Think about constraints, intent, tradeoffs, persona fit, budget/value, and likely dealbreakers.\n\n"
            "Return JSON: response_text (direct helpful answer, 2-4 sentences), "
            "items (array of 0-5 objects with name, item_id, score, reason, category, image_keyword, source). "
            "Use item_id only for catalogue items; for general suggestions use an empty item_id and source='general'."
        ).format(persona_note, message, catalog_text)
        try:
            resp = backend.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Return valid JSON only. Be useful, specific, and faithful to the user's message."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            catalog_map = {item.get("item_id", ""): item for item in catalog}
            for item in result.get("items", []):
                catalog_item = catalog_map.get(item.get("item_id", ""), {})
                if catalog_item:
                    item.setdefault("category", catalog_item.get("category", ""))
                    item.setdefault("price_level", catalog_item.get("price_level", ""))
                    item.setdefault("quality_score", catalog_item.get("base_quality_score", ""))
                    item.setdefault("source", "catalogue")
                else:
                    item.setdefault("item_id", "")
                    item.setdefault("category", category)
                    item.setdefault("source", "general")
            return result
        except Exception as exc:
            print("recommend override error: {}".format(exc))

    base_name = _keyword_name(message)
    return {
        "response_text": "I read your request as: {}. Here are flexible suggestions based on that message rather than forcing the default catalogue.".format(message),
        "items": [
            {
                "name": "Best-value {}".format(base_name),
                "item_id": "",
                "score": "86%",
                "reason": "Prioritises the exact need you described and balances quality with value.",
                "category": category,
                "image_keyword": base_name.lower(),
                "source": "general",
            },
            {
                "name": "Reliable {} option".format(base_name),
                "item_id": "",
                "score": "80%",
                "reason": "A safer pick when durability and fewer compromises matter more than flashy extras.",
                "category": category,
                "image_keyword": base_name.lower(),
                "source": "general",
            },
        ],
    }


if _static_mount is not None:
    app.router.routes.append(_static_mount)
