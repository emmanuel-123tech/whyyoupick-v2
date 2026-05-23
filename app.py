"""Vercel FastAPI entrypoint.

Vercel's Python runtime auto-detects FastAPI apps from app.py/index.py/server.py.
The original application lives in main.py for local Render/uvicorn usage. This
entrypoint also patches the Vercel routes that need free-form AI behavior.
"""

import json
import os
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


def _groq_models() -> List[str]:
    configured = os.getenv("GROQ_MODEL", "").strip()
    models = [configured, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    unique = []
    for model in models:
        if model and model not in unique:
            unique.append(model)
    return unique


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


def _image_url(keyword: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\s-]", " ", keyword or "product").strip() or "product"
    query = "+".join(clean.split()[:6])
    return "https://loremflickr.com/320/220/{}?lock={}".format(query, abs(hash(clean)) % 10000)


def _detect_language(message: str) -> str:
    msg = " {} ".format(message.lower())
    if any(word in msg for word in [" bawo ", " jare ", " e jowo ", " mo fe ", " nkan ", " ounje ", " owo "]):
        return "Yoruba"
    if any(word in msg for word in [" kedu ", " biko ", " achoro ", " ezigbo ", " nri ", " ego ", " maka "]):
        return "Igbo"
    if any(word in msg for word in [" sannu ", " ina ", " don Allah ", " abinci ", " kudi ", " lafiya ", " gida "]):
        return "Hausa"

    pidgin_strong = [" abeg ", " wetin ", " sabi ", " dey ", " no too ", " wahala "]
    pidgin_soft = [" make ", " na ", " sha ", " o "]
    if any(word in msg for word in pidgin_strong):
        return "Nigerian Pidgin"
    if sum(word in msg for word in pidgin_soft) >= 2:
        return "Nigerian Pidgin"
    return "English"


def _parse_json_response(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _chat_json(prompt: str, system: str) -> dict:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    last_error = None
    for model in _groq_models():
        try:
            response = backend.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            result = _parse_json_response(response.choices[0].message.content)
            result.setdefault("model_used", model)
            return result
        except Exception as json_error:
            last_error = json_error
            print("Groq model {} JSON-mode failed: {}".format(model, json_error))
            try:
                response = backend.client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                result = _parse_json_response(response.choices[0].message.content)
                result.setdefault("model_used", model)
                return result
            except Exception as text_error:
                last_error = text_error
                print("Groq model {} text retry failed: {}".format(model, text_error))
    raise last_error or RuntimeError("No Groq model completed successfully")


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
            "Return valid JSON only with: rating (float 1-5), review (2-4 natural sentences), "
            "confidence (string like 88%), reasoning (array of 3-4 specific strings), "
            "used_catalogue (boolean), interpreted_item (short string)."
        ).format(persona_note, item_ctx)
        try:
            result = _chat_json(prompt, "Return valid JSON only. Be specific to the user's item.")
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
    language = _detect_language(message)
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
            "You are WhyYouPick's intelligent Nigerian recommendation agent.\n{}\n\n"
            "User message: {}\n\n"
            "Detected reply language: {}. Reply naturally in this language. If the user mixes languages, you may code-switch in the same style. "
            "Supported languages: English, Yoruba, Igbo, Hausa, and Nigerian Pidgin.\n\n"
            "Relevant catalogue context, if useful:\n{}\n\n"
            "Respond to exactly what the user asked. If the catalogue is relevant, you may use catalogue items. "
            "If the user's request is outside or more specific than the catalogue, use general knowledge and say so naturally. "
            "Do not force the answer into the catalogue and do not recommend unrelated default items. "
            "Give detailed recommendation reviews, not one-line reasons. Each item must include: why it fits the message, what evidence or assumption supports it, what tradeoff to watch, and who it is best for. "
            "Use concrete Nigerian context when helpful, but do not invent exact prices or business claims as facts.\n\n"
            "Return valid JSON only with: language (string), response_text (friendly conversational answer, 3-5 sentences), "
            "items (array of 3-5 objects with: name, item_id, score, reason, detailed_review, best_for, watch_out, category, image_keyword, image_url, source). "
            "The visible UI currently shows the reason field, so reason must be a detailed 2-3 sentence mini-review, not a short phrase. "
            "Use item_id only for catalogue items; for general suggestions use an empty item_id and source='general'."
        ).format(persona_note, message, language, catalog_text)
        try:
            result = _chat_json(prompt, "Return valid JSON only. Be useful, specific, multilingual, and faithful to the user's message.")
            result.setdefault("language", language)
            result.setdefault("response_text", "Here are options that match what you asked for, with the main fit and tradeoff for each one.")
            result["agent_version"] = "recommendation-v2"
            catalog_map = {item.get("item_id", ""): item for item in catalog}
            for item in result.get("items", []):
                catalog_item = catalog_map.get(item.get("item_id", ""), {})
                keyword = item.get("image_keyword") or item.get("name") or category
                item.setdefault("image_keyword", keyword)
                item.setdefault("image_url", _image_url(keyword))
                if catalog_item:
                    item.setdefault("category", catalog_item.get("category", ""))
                    item.setdefault("price_level", catalog_item.get("price_level", ""))
                    item.setdefault("quality_score", catalog_item.get("base_quality_score", ""))
                    item.setdefault("source", "catalogue")
                else:
                    item.setdefault("item_id", "")
                    item.setdefault("category", category)
                    item.setdefault("source", "general")
                item.setdefault("detailed_review", item.get("reason", ""))
                item.setdefault("best_for", "Users who want a strong fit for this request.")
                item.setdefault("watch_out", "Check current availability, quality, and price before deciding.")
                if len(str(item.get("reason", ""))) < 120 and item.get("detailed_review"):
                    item["reason"] = item["detailed_review"]
            return result
        except Exception as exc:
            print("recommend override error: {}".format(exc))

    return _recommend_fallback(message, category, language)


def _recommend_fallback(message: str, category: str, language: str) -> dict:
    base_name = _keyword_name(message)
    intro_by_language = {
        "Yoruba": "Mo ye ohun ti o n wa. Eyi ni awon aba ti o ba ibeere naa mu, pelu idi, ohun ti o dara fun, ati ohun ti o ye ki o sayewo.",
        "Igbo": "Aghotara m ihe ichoro. Lee aro ndi dabara na mkpa gi, tinyere uru ha na ihe i kwesiri ilebara anya.",
        "Hausa": "Na fahimci abin da kake nema. Ga wasu shawarwari masu amfani tare da dalili da abin lura kafin ka zaba.",
        "Nigerian Pidgin": "I understand wetin you dey find. See better options wey match your request, plus why e make sense and wetin you suppose check before you choose.",
        "English": "I understand what you are looking for. Here are detailed options based on your request, with why each one fits and what to check before deciding.",
    }
    templates = [
        ("Best-value {}".format(base_name), "This is the practical first pick because it focuses on the exact need you described while balancing value and usefulness."),
        ("Reliable {} option".format(base_name), "This is the safer choice if consistency, fewer surprises, and dependable quality matter more than flashy extras."),
        ("Premium-leaning {}".format(base_name), "This fits when you want a more comfortable or higher-quality experience, but it may cost more than the basic option."),
    ]
    items = []
    for idx, (name, review) in enumerate(templates):
        keyword = "{} {}".format(base_name, category).strip().lower()
        detailed_review = "{} It matches the user's request for '{}'. I would compare current reviews, distance or availability, and total cost before making the final decision.".format(review, message)
        items.append({
            "name": name,
            "item_id": "",
            "score": "{}%".format(88 - idx * 5),
            "reason": detailed_review,
            "detailed_review": detailed_review,
            "best_for": "Someone who wants {} with a sensible balance of value and fit.".format(base_name.lower()),
            "watch_out": "Confirm recent reviews, real pricing, and availability because these can change quickly.",
            "category": category,
            "image_keyword": keyword,
            "image_url": _image_url(keyword),
            "source": "general",
        })
    return {
        "language": language,
        "agent_version": "recommendation-v2-fallback",
        "response_text": intro_by_language.get(language, intro_by_language["English"]),
        "items": items,
    }


if _static_mount is not None:
    app.router.routes.append(_static_mount)
