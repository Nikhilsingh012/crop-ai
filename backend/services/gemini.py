import base64
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _request(parts, generation_config=None):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Gemini is not configured. Add GEMINI_API_KEY to the project .env and restart the backend.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model)}:generateContent?key={quote(api_key)}"
    payload = {"contents": [{"role": "user", "parts": parts}]}
    if generation_config:
        payload["generationConfig"] = generation_config
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    payload = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            status = error.code
            if status in {400, 401, 403, 404}:
                raise RuntimeError(f"Gemini rejected the request (HTTP {status}). Check the API key, model name, and Gemini API access.") from None
            if attempt == 2:
                raise RuntimeError(f"Gemini is temporarily unavailable (HTTP {status}). Please try again in a moment.") from None
        except (URLError, OSError):
            # DNS lookups and TLS handshakes occasionally fail on the first try
            # from this host, so retry transient network errors.
            if attempt == 2:
                raise RuntimeError("Gemini could not be reached. Check the backend internet connection and try again.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            if attempt == 2:
                raise RuntimeError("Gemini returned an unreadable response. Please try again.") from None
        time.sleep(0.5 * (attempt + 1))
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini returned an unexpected response. Please try again.")

    candidates = payload.get("candidates", [])
    if not candidates:
        return None
    return "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))


def answer_question(question, evidence=None, language="en", diagnosis_context=None, conversation=None):
    evidence_text = json.dumps(evidence or [], ensure_ascii=False, indent=1)
    preliminary_context = json.dumps(diagnosis_context or {}, ensure_ascii=False)
    conversation_text = json.dumps(conversation or [], ensure_ascii=False)
    language_name = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}.get(language, "English")
    has_evidence = bool(evidence)
    return _request([
        {
            "text": (
                "You are Kheti, a friendly and practical agriculture assistant for Indian farmers, "
                f"home gardeners, and students. Reply in {language_name} using short paragraphs or a "
                "small numbered list. Be warm, specific, and useful.\n\n"
                "What you can do confidently:\n"
                "- Explain general agronomy: sowing, spacing, irrigation, mulching, soil preparation, "
                "crop rotation, composting, sunlight needs, harvesting signs, storage, and common pest or "
                "disease recognition based on symptoms the user describes.\n"
                "- Suggest organic, cultural, biological, and integrated-pest-management steps, and name "
                "active ingredients or product families where appropriate (for example a copper-based "
                "fungicide or neem oil) while telling the user to follow the product label.\n"
                "- Use the preliminary image analysis below as uncertain context and explain it in plain "
                "language.\n\n"
                "Strict limits:\n"
                "- Never give exact pesticide, fungicide, or fertilizer doses, spray concentrations, or "
                "mixing ratios. Say the label and a local KVK/agri-officer should confirm the dose.\n"
                "- Do not invent mandi prices, government scheme deadlines or eligibility, subsidy amounts, "
                "or live weather. If asked, say you cannot verify live figures and point to the relevant "
                "official source (Agmarknet for prices, the scheme portal for schemes, IMD for weather).\n"
                "- Do not claim certainty about a diagnosis. For serious spreading symptoms, advise a local "
                "agricultural extension officer or KVK and, where relevant, a plant clinic sample.\n\n"
                + (
                    "Verified reference extracts are supplied below. Prefer them for crop-specific facts "
                    "and cite their source URLs inline.\n"
                    if has_evidence else
                    "No verified reference extracts were retrieved for this question. You may still give "
                    "general, clearly-labelled guidance from widely accepted agronomy practice, and say "
                    "plainly that it is general guidance rather than a verified local recommendation.\n"
                )
                + f"\nVerified reference extracts: {evidence_text}\n"
                f"Preliminary image analysis (uncertain, not verified): {preliminary_context}\n"
                f"Recent conversation (context only, not evidence): {conversation_text}\n"
                f"Current question: {question}"
            )
        }
    ])


def diagnose_image(image_bytes, model_result=None, mime_type="image/jpeg"):
    text = _request([
        {
            "text": (
                "You are Gemini Vision, assisting a farmer in India. Inspect the attached image itself. "
                "Identify the crop and the most likely visible disease or state that no disease is clearly visible. "
                "Give practical, cautious cure guidance based on visible evidence. Do not claim certainty, "
                "invent a diagnosis when the image is unclear, recommend a precise pesticide or fertilizer "
                "dose, or claim that a treatment is officially approved. If uncertain, say so in the disease "
                "name and explain that the farmer should get the plant checked locally. Keep each field concise. "
                "Return exactly the requested structured fields."
            )
        },
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
    ], generation_config={
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "OBJECT",
            "properties": {
                "crop_name": {"type": "STRING", "description": "Name of the crop visible in the image, or Unknown."},
                "disease_name": {"type": "STRING", "description": "Most likely visible disease, healthy appearance, or an uncertainty statement."},
                "cure": {"type": "STRING", "description": "Practical, cautious care and treatment guidance; no invented chemical doses."},
            },
            "required": ["crop_name", "disease_name", "cure"],
            "propertyOrdering": ["crop_name", "disease_name", "cure"],
        },
    })
    if not text:
        raise RuntimeError("Gemini did not return a diagnosis. Try a clear, well-lit crop image.")
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RuntimeError("Gemini Vision returned an invalid diagnosis response.") from error
    if not isinstance(result, dict):
        raise RuntimeError("Gemini Vision returned an unexpected diagnosis response.")
    normalized = {
        key: str(result.get(key, "")).strip()
        for key in ("crop_name", "disease_name", "cure")
    }
    if any(not value for value in normalized.values()):
        raise RuntimeError("Gemini Vision returned an incomplete diagnosis. Please try the scan again.")
    return normalized
