import json

import torch
from torch import nn
from torch.utils.data import DataLoader
from torchvision import models, transforms

from augmentation import TRAIN_TRANSFORM
from config import BATCH_SIZE, CHECKPOINT_PATH, EPOCHS, LEARNING_RATE
from dataset import build_dataset


def main():
    dataset = build_dataset("train")
    dataset.transform = TRAIN_TRANSFORM
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)

    model = models.resnet18(weights="DEFAULT")
    model.fc = nn.Linear(model.fc.in_features, len(dataset.classes))
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(EPOCHS):
        running_loss = 0.0
        for images, labels in loader:
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
        print(f"epoch={epoch + 1}/{EPOCHS} loss={running_loss / len(loader):.4f}")

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": dataset.classes}, CHECKPOINT_PATH)
    CHECKPOINT_PATH.with_suffix(".classes.json").write_text(json.dumps(dataset.classes, indent=2))
    print(f"Saved checkpoint to {CHECKPOINT_PATH}")


if __name__ == "__main__":
    main()
