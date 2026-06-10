"""Local embeddings via fastembed — CPU, free, no API. Lazy-imported so the rest
of the app (and host tooling) works without the heavy dependency installed."""

import logging

log = logging.getLogger("cale.embed")

MODEL_NAME = "BAAI/bge-small-en-v1.5"   # 384-dim, small, strong, CPU-friendly
DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        log.info("loading embedding model %s (first run downloads it)", MODEL_NAME)
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def embed(texts):
    """Return a list of float vectors for the given texts."""
    model = _get_model()
    return [list(map(float, v)) for v in model.embed(list(texts))]
