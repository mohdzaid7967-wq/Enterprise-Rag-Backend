import csv
import time
from typing import List
from app.database import SessionLocal
from app import crud, models
from app.embedding import get_embedding
from app.reranker import rerank_chunks

def evaluate_rag_pipeline():
    db = SessionLocal()

    # Locate active user with uploaded policy document
    doc = db.query(models.Document).first()
    if not doc:
        print("--> Error: No documents found in database. Upload a document first.")
        db.close()
        return

    user_id = doc.user_id
    print(f"Starting Phase 10 Evaluation for Document #{doc.id} (Owner: User #{user_id})\n")

    questions = []
    with open("eval_questions.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            questions.append(row)

    total_questions = len(questions)
    hits_at_5 = 0
    reciprocal_ranks = []
    latencies = []

    print(f"{'ID':<3} | {'Query':<42} | {'Rank':<6} | {'Hit@5':<5} | {'Latency':<8}")
    print("-" * 75)

    evaluation_output = []

    for item in questions:
        q_id = item["id"]
        query = item["question"]
        target = item["target_keyword"].lower()

        start_time = time.perf_counter()

        # Step 1: Candidate Vector Retrieval
        q_vec = get_embedding(query)
        candidates = crud.search_similar_chunks(db=db, query_embedding=q_vec, user_id=user_id, limit=10)

        # Step 2: Rerank top 5
        reranked = rerank_chunks(query=query, chunks=candidates, top_k=5)
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        latencies.append(elapsed_ms)

        # Find rank of target keyword
        found_rank = None
        for rank_idx, (chunk, score) in enumerate(reranked, 1):
            if target in chunk.content.lower():
                found_rank = rank_idx
                break

        # Calculate metrics
        is_hit = 1 if (found_rank is not None and found_rank <= 5) else 0
        hits_at_5 += is_hit

        rr = (1.0 / found_rank) if found_rank else 0.0
        reciprocal_ranks.append(rr)

        rank_display = str(found_rank) if found_rank else ">5"
        hit_display = "YES" if is_hit else "NO"
        print(f"{q_id:<3} | {query[:42]:<42} | {rank_display:<6} | {hit_display:<5} | {elapsed_ms:>6.1f}ms")

        evaluation_output.append({
            "id": q_id,
            "question": query,
            "target_keyword": item["target_keyword"],
            "rank": rank_display,
            "hit_at_5": is_hit,
            "reciprocal_rank": round(rr, 4),
            "latency_ms": round(elapsed_ms, 2)
        })

    db.close()

    # Aggregate Metrics Calculation
    hit_rate_5 = (hits_at_5 / total_questions) * 100
    mrr = sum(reciprocal_ranks) / total_questions
    avg_latency = sum(latencies) / total_questions

    print("\n" + "=" * 45)
    print("           EVALUATION SUMMARY")
    print("=" * 45)
    print(f" Total Evaluated Queries : {total_questions}")
    print(f" Hit@5 / Recall@5        : {hit_rate_5:.2f}%")
    print(f" Mean Reciprocal Rank    : {mrr:.4f}")
    print(f" Average Latency         : {avg_latency:.2f} ms")
    print("=" * 45)

    # Save detailed evaluation log
    with open("eval_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, 
            fieldnames=["id", "question", "target_keyword", "rank", "hit_at_5", "reciprocal_rank", "latency_ms"]
        )
        writer.writeheader()
        writer.writerows(evaluation_output)

    print("\n--> Detailed logs exported to eval_results.csv")

if __name__ == "__main__":
    evaluate_rag_pipeline()