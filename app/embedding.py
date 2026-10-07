from typing import List
from fastembed import TextEmbedding

# Downloads once (~130MB) and runs locally without any API key
_model = None

def get_model():
    global _model
    if _model is None:
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _model

def get_embedding(text: str) -> List[float]:
    """Generates an embedding vector for a single query string."""
    model = get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()

def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generates embeddings for multiple chunks in one efficient pass."""
    if not texts:
        return []
    model = get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]