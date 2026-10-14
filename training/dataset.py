from pathlib import Path

from torchvision import datasets

from config import DATA_DIR, IMAGE_SIZE


def build_dataset(split="train"):
    split_dir = DATA_DIR / split
    if not split_dir.exists():
        raise FileNotFoundError(
            f"Dataset split not found: {split_dir}. "
            "Add folders such as data/train/Tomato___Early_blight."
        )

    return datasets.ImageFolder(split_dir)
