from flask import Blueprint, jsonify, request
from authz import current_user_id

from db import save_chat
from db import get_user
from services.gemini import answer_question
from services.crop_catalog import load_catalog, normalize_text
from services.rag.retriever import INDEX_PATH, retrieve

chat_bp = Blueprint("chat", __name__)


@chat_bp.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 4000:
        return jsonify({"error": "A question is required and must be under 4,000 characters."}), 400

    user_id = current_user_id()
    user = get_user(user_id) if user_id else None
    language = payload.get("language", (user or {}).get("preferred_language", "en"))
    if language not in {"en", "hi", "hinglish"}:
        return jsonify({"error": "language must be en, hi, or hinglish."}), 400
    supplied_diagnosis = payload.get("diagnosis_context") or {}
    if not isinstance(supplied_diagnosis, dict):
        return jsonify({"error": "diagnosis_context must be an object."}), 400
    diagnosis_context = {key: str(supplied_diagnosis[key])[:500] for key in ("crop", "disease", "symptoms", "model_status") if supplied_diagnosis.get(key) is not None}
    normalized_question = f" {normalize_text(message)} "
    crop_matches = {}
    for item in load_catalog():
        for alias in [item["canonical_name"], item["crop_id"].replace("_", " "), *item.get("aliases", [])]:
            normalized_alias = normalize_text(alias)
            if normalized_alias and f" {normalized_alias} " in normalized_question:
                crop_matches[item["crop_id"]] = item
                break
    evidence = []
    if len(crop_matches) == 1 and INDEX_PATH.exists():
        crop = next(iter(crop_matches.values()))
        try:
            records = retrieve(crop["canonical_name"], message, top_k=3)
            evidence = [{"text": item["text"], "source_url": item["metadata"].get("source_url"), "source": item["metadata"].get("source"), "crop_id": item["metadata"].get("crop_id")} for item in records]
        except Exception:
            evidence = []
    if len(crop_matches) > 1:
        evidence = []
    fallback = "I could not find verified source material for a crop-specific answer. Share the crop and symptoms, or check with your local agriculture extension office."
    try:
        answer = answer_question(message, evidence=evidence, language=language, diagnosis_context=diagnosis_context) or fallback
        source = "gemini" if answer != fallback else "starter-agriculture-assistant"
    except Exception:
        answer = fallback
        source = "starter-agriculture-assistant"
    try:
        record = save_chat(message, answer, source, user_id=user_id)
    except Exception:
        record = None
    return jsonify({"answer": answer, "source": source, "evidence": [{"source": item.get("source"), "source_url": item.get("source_url")} for item in evidence], "message": record})
