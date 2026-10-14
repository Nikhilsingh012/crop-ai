"""Load explicitly labeled, crop-specific source files for the local RAG index."""
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from services.crop_catalog import crop_by_id

ROOT = Path(__file__).resolve().parents[3]
SOURCES_PATH = ROOT / "data" / "crop_knowledge" / "sources"
SUPPORTED_EXTENSIONS = {".csv", ".json", ".txt", ".md", ".pdf"}


def _read_source(path):
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in csv.DictReader(handle))
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("text"), str):
            return payload["text"]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return path.read_text(encoding="utf-8").strip()


def load_source_documents(source_root=SOURCES_PATH):
    """Each source file requires a neighboring `<filename>.metadata.json` sidecar."""
    root = Path(source_root)
    if not root.exists():
        return []
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS and not item.name.endswith(".metadata.json")):
        metadata_path = path.with_name(path.name + ".metadata.json")
        if not metadata_path.exists():
            raise ValueError(f"Missing source metadata sidecar: {metadata_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        crop_id = metadata.get("crop_id")
        crop = crop_by_id(crop_id)
        if crop is None:
            raise ValueError(f"Unknown crop_id in source metadata: {crop_id!r}")
        source_url = metadata.get("source_url")
        if not metadata.get("source") or not source_url:
            raise ValueError(f"Source title and source_url are required in {metadata_path}")
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid source_url in {metadata_path}")
        text = _read_source(path)
        if not text:
            raise ValueError(f"Source file is empty or has no extractable text: {path}")
        records.append({
            "crop_id": crop_id,
            "crop": crop["canonical_name"].lower(),
            "canonical_name": crop["canonical_name"],
            "aliases": crop.get("aliases", []),
            "region": metadata.get("region"),
            "stage": metadata.get("stage"),
            "risk_type": metadata.get("risk_type"),
            "source": metadata.get("source") or path.name,
            "source_url": source_url,
            "source_file": str(path.relative_to(root)),
            "text": text,
        })
    return records
