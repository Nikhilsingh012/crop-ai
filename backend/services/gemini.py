import base64
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


def _request(parts):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model)}:generateContent?key={quote(api_key)}"
    body = json.dumps({"contents": [{"role": "user", "parts": parts}]}).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise RuntimeError("Gemini Vision could not analyze the image.") from error

    candidates = payload.get("candidates", [])
    if not candidates:
        return None
    return "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))


def answer_question(question, evidence=None, language="en", diagnosis_context=None):
    evidence_text = json.dumps(evidence or [], ensure_ascii=False)
    preliminary_context = json.dumps(diagnosis_context or {}, ensure_ascii=False)
    language_name = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}.get(language, "English")
    return _request([
        {
            "text": (
                f"You are an Indian agriculture decision-support assistant. Answer clearly and briefly in {language_name}. "
                "Never claim certainty and never provide exact pesticide or fertilizer doses. "
                "Use only the cited evidence supplied below for factual crop-specific claims. Cite relevant "
                "Treat image-analysis details as preliminary and uncertain context, not verified evidence. "
                "items with their source URLs. You do not have live access to "
                "government scheme deadlines, eligibility, mandi prices, or current weather; do not "
                "invent these facts. Say when evidence is missing and direct the user to the relevant "
                "official source. Distinguish general guidance from a diagnosis. If evidence is empty, "
                "state that you cannot verify a crop-specific answer. "
                f"Verified retrieved evidence: {evidence_text}\nPreliminary image context: {preliminary_context}\nQuestion: {question}"
            )
        }
    ])


def diagnose_image(image_bytes, model_result=None, mime_type="image/jpeg"):
    local_context = json.dumps(model_result or {"crop": "Unknown", "disease": "Unknown"})
    text = _request([
        {
            "text": (
                "Inspect this crop image as a second opinion for a crop-disease classifier. "
                f"The local ML model predicted this context: {local_context}. "
                "Return only valid JSON with keys crop, disease, confidence, severity, symptoms, "
                "possible_cause, prevention, treatment, recommended_action, agreement. "
                "Use the local prediction when the image supports it, but correct it when the visual "
                "evidence clearly disagrees. Set agreement to true only when crop and disease agree. "
                "If uncertain, use Unknown and explain uncertainty. Never invent chemical or fertilizer doses."
            )
        },
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
    ])
    if not text:
        return None
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RuntimeError("Gemini Vision returned an invalid diagnosis response.") from error
    if not isinstance(result, dict):
        raise RuntimeError("Gemini Vision returned an unexpected diagnosis response.")
    return result
