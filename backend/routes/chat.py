import os

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
    supplied_conversation = payload.get("conversation", [])
    if not isinstance(supplied_conversation, list):
        return jsonify({"error": "conversation must be a list of recent messages."}), 400
    conversation = []
    for item in supplied_conversation[-8:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            conversation.append({"role": item["role"], "content": content.strip()[:1200]})
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
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return jsonify({"error": "Gemini is not configured on the backend. Set GEMINI_API_KEY in the project .env and restart the server."}), 503
    try:
        answer = answer_question(message, evidence=evidence, language=language, diagnosis_context=diagnosis_context, conversation=conversation)
        if not answer:
            return jsonify({"error": "Gemini returned no answer. Please try again."}), 503
        source = "gemini"
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503
    try:
        record = save_chat(message, answer, source, user_id=user_id)
    except Exception:
        record = None
    return jsonify({"answer": answer, "source": source, "evidence": [{"source": item.get("source"), "source_url": item.get("source_url")} for item in evidence], "message": record})
