import torch
from torch.utils.data import DataLoader

from augmentation import EVAL_TRANSFORM
from dataset import build_dataset


def main():
    dataset = build_dataset("val")
    dataset.transform = EVAL_TRANSFORM
    loader = DataLoader(dataset, batch_size=32, shuffle=False, num_workers=0)
    print(f"Validation samples: {len(dataset)}")
    print(f"Classes: {len(dataset.classes)}")
    print("Load the saved checkpoint here to calculate accuracy and confusion matrices.")


if __name__ == "__main__":
    main()
