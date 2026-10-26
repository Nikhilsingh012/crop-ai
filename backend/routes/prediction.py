import os

from flask import Blueprint, jsonify, request
from authz import current_user_id

from db import save_scan
from services.model import predict
from services.preprocessing import validate_image
from services.gemini import diagnose_image

prediction_bp = Blueprint("prediction", __name__)


@prediction_bp.post("/predict")
def predict_disease():
    image = request.files.get("image")
    if image is None:
        return jsonify({"error": "Upload an image using the 'image' field."}), 400

    try:
        image_bytes = validate_image(image)
        if os.getenv("GEMINI_API_KEY", "").strip():
            vision_result = diagnose_image(image_bytes, mime_type=image.mimetype or "image/jpeg")
            crop_name = vision_result["crop_name"]
            disease_name = vision_result["disease_name"]
            cure = vision_result["cure"]
            result = {
                "crop": crop_name,
                "crop_name": crop_name,
                "disease": disease_name,
                "disease_name": disease_name,
                "treatment": cure,
                "cure": cure,
                "healthy": disease_name.casefold() in {"healthy", "no disease", "no disease visible", "no visible disease detected"},
                "confidence": None,
                "model_status": "gemini-vision",
                "recommendations": [cure],
            }
        else:
            result = predict(image_bytes, filename=image.filename)
            result["recommendations"] = result.get("recommendations", []) + [
                "Gemini Vision is not configured. Add GEMINI_API_KEY to the project .env and restart the backend."
            ]
        try:
            result["scan"] = save_scan(result, filename=image.filename, user_id=current_user_id())
        except Exception:
            result["database_status"] = "unavailable"
        return jsonify(result)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503
