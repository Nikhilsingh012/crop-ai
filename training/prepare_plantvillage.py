"""Prepare an extracted PlantVillage dataset for the existing ImageFolder trainer.

Download PlantVillage from its official publication/repository separately, then run:
python training/prepare_plantvillage.py --source <extracted-folder>
"""

import argparse
import random
import shutil
from pathlib import Path

from config import DATA_DIR


def prepare(source, validation_ratio=0.2, seed=42):
    source = Path(source)
    images = sorted(path for path in source.rglob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not images:
        raise FileNotFoundError(f"No image files found under {source}")
    random.Random(seed).shuffle(images)
    split_at = max(1, int(len(images) * (1 - validation_ratio)))
    for split, paths in (("train", images[:split_at]), ("val", images[split_at:])):
        for image in paths:
            label = image.parent.name
            target = DATA_DIR / split / label / image.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, target)
    print(f"Prepared {len(images)} images in {DATA_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Extracted PlantVillage directory")
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    args = parser.parse_args()
    prepare(args.source, args.validation_ratio)