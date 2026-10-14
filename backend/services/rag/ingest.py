import json
from pathlib import Path

from .embeddings import embed
from .knowledge_loader import document_text, load_documents
from .source_ingest import load_source_documents
from services.crop_catalog import validate_catalog

ROOT = Path(__file__).resolve().parents[3]
INDEX_PATH = ROOT / "data" / "crop_knowledge" / "index.json"


def build_index():
    catalog = validate_catalog()
    # Legacy threshold records remain useful for review but are not evidence until
    # a source-backed record explicitly marks its thresholds verified.
    documents = [document for document in load_documents() if document.get("threshold_evidence_status") == "verified" and document.get("source_url")]
    documents.extend(load_source_documents())
    registered_ids = {crop["crop_id"] for crop in catalog}
    invalid = [document.get("crop", "unknown") for document in documents if document.get("crop_id") not in registered_ids]
    if invalid:
        raise ValueError(f"Knowledge records refer to unregistered crops: {', '.join(invalid)}")
    records = [{"metadata": document, "text": document.get("text") or document_text(document), "embedding": embed(document.get("text") or document_text(document))} for document in documents]
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(records), encoding="utf-8")
    return len(records)


if __name__ == "__main__":
    print(f"Indexed {build_index()} crop knowledge documents at {INDEX_PATH}")
