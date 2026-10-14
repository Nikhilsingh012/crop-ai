import hashlib
import math
import os
from pathlib import Path

DIMENSIONS = 256


def _tokens(text):
    return [token for token in "".join(character.lower() if character.isalnum() else " " for character in text).split() if token]


def embed(text):
    """Use a configured local model, otherwise a deterministic offline lexical vector."""
    model_path = os.getenv("RAG_EMBEDDING_MODEL_PATH")
    if model_path and Path(model_path).is_dir():
        from sentence_transformers import SentenceTransformer
        if not hasattr(embed, "model"):
            embed.model = SentenceTransformer(model_path, local_files_only=True)
        return embed.model.encode([text], normalize_embeddings=True)[0].tolist()
    vector = [0.0] * DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % DIMENSIONS
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
