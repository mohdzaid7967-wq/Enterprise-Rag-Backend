from app.database import SessionLocal
from app import models

db = SessionLocal()
users = db.query(models.User).all()
print("Registered Users:")
for u in users:
    doc_count = db.query(models.Document).filter(models.Document.user_id == u.id).count()
    print(f" - User ID: {u.id} | Email: {u.email} | Documents: {doc_count}")

chunk_count = db.query(models.DocumentChunk).count()
print(f"\nTotal Chunks in DB: {chunk_count}")

if chunk_count > 0:
    sample = db.query(models.DocumentChunk).first()
    print(f"Sample Chunk Text:\n{sample.content[:150]}...")
db.close()