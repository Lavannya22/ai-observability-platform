"""
Sentence Transformer embeddings for log messages.

Model: all-MiniLM-L6-v2  (384-dimensional, fast, good semantic quality)
"""
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed(messages: list[str], batch_size: int = 64) -> np.ndarray:
    """
    Encode a list of log message strings into 384-dim embedding vectors.

    Returns shape (len(messages), 384).
    """
    model = _get_model()
    return model.encode(messages, batch_size=batch_size, show_progress_bar=False)
