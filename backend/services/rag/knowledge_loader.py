import json
from pathlib import Path
from services.crop_catalog import resolve_crop

ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_PATH = ROOT / "data" / "crop_knowledge" / "crops.json"


def load_documents():
    with KNOWLEDGE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_document(crop):
    resolved, _ = resolve_crop(crop)
    if not resolved:
        return None
    return next((item for item in load_documents() if item.get("crop_id") == resolved["crop_id"]), None)


def document_text(document):
    return json.dumps(document, ensure_ascii=True, sort_keys=True)
