import csv
from app.database import SessionLocal
from app import crud, models
from app.embedding import get_embedding
from app.reranker import rerank_chunks

test_queries = [
    {"query": "What is the purpose of the leave policy?", "target_keyword": "purpose"},
    {"query": "Who is eligible for leave benefits?", "target_keyword": "eligibility"},
    {"query": "What is the leave entitlement for employees?", "target_keyword": "entitlement"},
    {"query": "What is the scope of this policy?", "target_keyword": "scope"},
]

def run_evaluation():
    db = SessionLocal()

    doc = db.query(models.Document).first()
    if not doc:
        print("--> Error: No documents found.")
        db.close()
        return

    active_user_id = doc.user_id
    print(f"Evaluating chunks for Document ID: {doc.id} (Owner User ID: {active_user_id})")

    evaluation_records = []
    print(f"\n{'Query':<45} | {'Vector Rank':<12} | {'Reranked Rank':<14} | Result")
    print("-" * 85)

    for item in test_queries:
        q = item["query"]
        target = item["target_keyword"].lower()

        # 1. Vector candidates (fetch pool of 10)
        q_vec = get_embedding(q)
        vector_candidates = crud.search_similar_chunks(
            db=db,
            query_embedding=q_vec,
            user_id=active_user_id,
            limit=10
        )

        vec_rank = "Not Found"
        for idx, c in enumerate(vector_candidates):
            if target in c.content.lower():
                vec_rank = idx + 1
                break

        # 2. Cross-Encoder rerank
        reranked = rerank_chunks(query=q, chunks=vector_candidates, top_k=10)
        rerank_pos = "Not Found"
        for idx, (c, score) in enumerate(reranked):
            if target in c.content.lower():
                rerank_pos = idx + 1
                break

        improved = "N/A"
        if isinstance(vec_rank, int) and isinstance(rerank_pos, int):
            if rerank_pos < vec_rank:
                improved = "Yes (Improved)"
            elif rerank_pos == vec_rank:
                improved = "Maintained"
            else:
                improved = "Dropped"

        print(f"{q[:45]:<45} | {str(vec_rank):<12} | {str(rerank_pos):<14} | {improved}")

        evaluation_records.append({
            "query": q,
            "target_keyword": item["target_keyword"],
            "vector_rank": vec_rank,
            "reranked_rank": rerank_pos,
            "result": improved
        })

    db.close()

    with open("reranker_evaluation.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["query", "target_keyword", "vector_rank", "reranked_rank", "result"]
        )
        writer.writeheader()
        writer.writerows(evaluation_records)

    print("\n--> Successfully saved results to reranker_evaluation.csv")

if __name__ == "__main__":
    run_evaluation()