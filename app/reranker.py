from typing import List, Tuple, Any
from sentence_transformers import CrossEncoder

# Downloaded once locally (~80MB); reads (query, chunk) pairs simultaneously
_reranker_model = None

def get_reranker() -> CrossEncoder:
    global _reranker_model
    if _reranker_model is None:
        _reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker_model

def rerank_chunks(query: str, chunks: List[Any], top_k: int = 3) -> List[Tuple[Any, float]]:
    """
    Reranks candidate chunks by relevance to query.
    Returns: list of tuples (chunk_object, rerank_score) sorted descending by score.
    """
    if not chunks:
        return []

    model = get_reranker()
    pairs = [[query, chunk.content] for chunk in chunks]
    scores = model.predict(pairs)

    scored_chunks = list(zip(chunks, [float(s) for s in scores]))
    scored_chunks.sort(key=lambda x: x[1], reverse=True)

    return scored_chunks[:top_k]