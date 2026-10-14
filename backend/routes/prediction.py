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
        ml_result = predict(image_bytes, filename=image.filename)
        result = dict(ml_result)
        result["ml_prediction"] = {
            "crop": ml_result.get("crop"),
            "disease": ml_result.get("disease"),
            "confidence": ml_result.get("confidence", 0),
            "model_status": ml_result.get("model_status"),
        }

        if os.getenv("GEMINI_API_KEY"):
            try:
                vision_result = diagnose_image(image_bytes, model_result=ml_result, mime_type=image.mimetype)
            except RuntimeError as error:
                vision_result = None
                result["vision_error"] = str(error)
            if vision_result:
                vision_confidence = vision_result.get("confidence", ml_result.get("confidence", 0))
                try:
                    vision_confidence = round(float(vision_confidence), 4)
                except (TypeError, ValueError):
                    vision_confidence = ml_result.get("confidence", 0)
                result.update({
                    "crop": ml_result.get("crop") if ml_result.get("model_status") == "checkpoint" else vision_result.get("crop", ml_result.get("crop")),
                    "disease": ml_result.get("disease") if ml_result.get("model_status") == "checkpoint" else vision_result.get("disease", ml_result.get("disease")),
                    "confidence": ml_result.get("confidence", 0) if ml_result.get("model_status") == "checkpoint" else vision_confidence,
                    "healthy": str(result.get("disease", "")).lower() in {"healthy", "normal"},
                    "symptoms": vision_result.get("symptoms", []),
                    "possible_cause": vision_result.get("possible_cause", ""),
                    "prevention": vision_result.get("prevention", ""),
                    "treatment": vision_result.get("treatment", ""),
                    "recommended_action": vision_result.get("recommended_action", ""),
                    "agreement": vision_result.get("agreement"),
                    "vision_analysis": vision_result,
                    "model_status": "ml+gemini-vision",
                    "recommendations": [vision_result.get("recommended_action") or "Confirm uncertain cases with a local agriculture expert."],
                })
        if result.get("model_status") != "ml+gemini-vision":
            result["recommendations"] = result.get("recommendations", []) + [
                "Gemini Vision is not configured; add GEMINI_API_KEY for symptoms, cure, and prevention guidance."
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
