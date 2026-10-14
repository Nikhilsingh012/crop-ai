import json
import math
from pathlib import Path

from .embeddings import embed
from .ingest import INDEX_PATH, build_index
from services.crop_catalog import resolve_crop
from services.crop_catalog import normalize_text


def _similarity(left, right):
    return sum(a * b for a, b in zip(left, right)) / ((math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))) or 1.0)


def retrieve(crop, query="", top_k=3, region=None, stage=None):
    if not INDEX_PATH.exists():
        build_index()
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    resolved, _ = resolve_crop(crop)
    if not resolved:
        return []
    records = [record for record in records if record["metadata"].get("crop_id") == resolved["crop_id"]]
    records = [record for record in records if record["metadata"].get("source_url") and (record["metadata"].get("source_file") or record["metadata"].get("threshold_evidence_status") == "verified")]
    if not records:
        return []
    for field, requested in (("region", region), ("stage", stage)):
        if not requested:
            continue
        matching = [record for record in records if normalize_text(record["metadata"].get(field)) == normalize_text(requested)]
        if matching:
            records = matching
        else:
            general = [record for record in records if not record["metadata"].get(field)]
            if general:
                records = general
    searchable_names = " ".join([resolved["canonical_name"], *resolved.get("aliases", [])])
    vector = embed(f"{searchable_names} {query}")
    return sorted(records, key=lambda record: _similarity(vector, record["embedding"]), reverse=True)[:top_k]
