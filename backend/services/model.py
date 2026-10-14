from pathlib import Path
from io import BytesIO

from PIL import Image

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "crop_disease_model.pth"
IMAGE_SIZE = 224


def _decode_label(label):
    parts = str(label).split("___", 1)
    return parts[0].replace("_", " "), parts[1].replace("_", " ") if len(parts) == 2 else "Unknown"


def predict(image_bytes, filename=None):
    """Return a deterministic starter response until a trained checkpoint is available."""
    if not MODEL_PATH.exists():
        return {
            "crop": "Unknown",
            "disease": "Model not trained yet",
            "healthy": False,
            "confidence": 0.0,
            "recommendations": [
                "Add a trained checkpoint at backend/models/crop_disease_model.pth.",
                "Run the training pipeline in training/train.py.",
                "Use a clear, well-lit image of one leaf for the next scan.",
            ],
            "model_status": "demo",
        }

    try:
        import torch
        from torchvision import models, transforms
    except ImportError as error:
        raise RuntimeError("The trained model dependencies are unavailable.") from error

    checkpoint = torch.load(MODEL_PATH, map_location="cpu")
    classes = checkpoint.get("classes")
    state_dict = checkpoint.get("state_dict")
    if not classes or state_dict is None:
        raise RuntimeError("The checkpoint must contain classes and state_dict.")

    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, len(classes))
    model.load_state_dict(state_dict)
    model.eval()
    transform = transforms.Compose([
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    with Image.open(BytesIO(image_bytes)).convert("RGB") as image:
        tensor = transform(image).unsqueeze(0)
    with torch.no_grad():
        probabilities = torch.softmax(model(tensor), dim=1)[0]
    confidence, index = probabilities.max(dim=0)
    crop, disease = _decode_label(classes[index.item()])
    return {
        "crop": crop,
        "disease": disease,
        "healthy": disease.lower() in {"healthy", "normal"},
        "confidence": round(float(confidence), 4),
        "recommendations": ["Use the result as decision support and confirm uncertain cases locally."],
        "model_status": "checkpoint",
    }
