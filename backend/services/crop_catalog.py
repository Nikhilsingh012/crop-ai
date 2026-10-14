"""Canonical crop registry shared by API, knowledge lookup and the UI."""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data" / "crops" / "crop_catalog.json"


def normalize_text(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def resolve_crop(value):
    key = normalize_text(value)
    if not key:
        return None, []
    ambiguous = {
        "tori": ["ridge_gourd", "sponge_gourd"],
        "gobhi": ["cabbage", "cauliflower"],
        "methi": ["fenugreek_leaves", "fenugreek_seed"],
        "chilli": ["green_chilli", "dry_chilli"],
        "chili": ["green_chilli", "dry_chilli"],
    }
    if key in ambiguous:
        return None, [crop_by_id(crop_id)["canonical_name"] for crop_id in ambiguous[key] if crop_by_id(crop_id)]
    matches = []
    variants = {key}
    if key.endswith("ies") and len(key) > 4:
        variants.add(key[:-3] + "y")
    if key.endswith("oes") and len(key) > 4:
        variants.add(key[:-2])
    if key.endswith("s") and len(key) > 3:
        variants.add(key[:-1])
    else:
        variants.add(key + "s")
    for crop in load_catalog():
        names = [crop["crop_id"].replace("_", " "), crop["canonical_name"], *crop.get("aliases", [])]
        if variants.intersection(normalize_text(name) for name in names):
            matches.append(crop)
    return (matches[0] if len(matches) == 1 else None), [item["canonical_name"] for item in matches]


def crop_by_id(crop_id):
    return next((item for item in load_catalog() if item["crop_id"] == crop_id), None)


def validate_catalog():
    catalog = load_catalog()
    ids = [item.get("crop_id") for item in catalog]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate crop IDs in crop catalog.")
    owners = {}
    for item in catalog:
        for name in [item["canonical_name"], item["crop_id"].replace("_", " "), *item.get("aliases", [])]:
            key = normalize_text(name)
            if key in owners and owners[key] != item["crop_id"]:
                raise ValueError(f"Conflicting crop alias {name!r}: {owners[key]} and {item['crop_id']}.")
            owners[key] = item["crop_id"]
    return catalog
