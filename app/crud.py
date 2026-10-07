import bcrypt
from sqlalchemy.orm import Session
from app import models, schemas
from typing import List, Optional, Dict, Any
from app.embedding import get_embeddings_batch
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app import models, schemas
from app.embedding import get_embeddings_batch

def get_password_hash(password: str) -> str:
    # bcrypt requires bytes and has a 72-byte max limit
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_pwd = get_password_hash(user.password)
    db_user = models.User(
        name=user.name,
        email=user.email,
        password_hash=hashed_pwd
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def create_document(
    db: Session,
    user_id: int,
    filename: str,
    file_type: str,
    status: models.DocumentStatus = models.DocumentStatus.UPLOADED
) -> models.Document:
    doc = models.Document(
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        status=status
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

def get_user_documents(db: Session, user_id: int) -> List[models.Document]:
    # Ensure users only retrieve their own documents
    return db.query(models.Document).filter(models.Document.user_id == user_id).all()

def get_user_document_by_id(db: Session, document_id: int, user_id: int) -> Optional[models.Document]:
    # Ensure ownership check
    return db.query(models.Document).filter(
        models.Document.id == document_id,
        models.Document.user_id == user_id
    ).first()

def delete_user_document(db: Session, document_id: int, user_id: int) -> bool:
    doc = get_user_document_by_id(db, document_id=document_id, user_id=user_id)
    if not doc:
        return False
    db.delete(doc)
    db.commit()
    return True


def store_document_chunks(
    db: Session,
    document_id: int,
    chunks: List[Dict[str, Any]]
) -> List[models.DocumentChunk]:
    if not chunks:
        return []

    contents = [c["content"] for c in chunks]
    embeddings = get_embeddings_batch(contents)

    db_chunks = []
    for idx, c in enumerate(chunks):
        db_chunk = models.DocumentChunk(
            document_id=document_id,
            chunk_index=c["chunk_index"],
            content=c["content"],
            page_number=c.get("page_number"),
            section=c.get("section"),
            embedding=embeddings[idx] if embeddings else None
        )
        db.add(db_chunk)
        db_chunks.append(db_chunk)

    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if doc:
        doc.status = models.DocumentStatus.READY

    db.commit()
    return db_chunks

def search_similar_chunks(
    db: Session,
    query_embedding: List[float],
    user_id: int,
    limit: int = 5
) -> List[models.DocumentChunk]:
    # 1. Fetch chunks belonging strictly to this user
    chunks = (
        db.query(models.DocumentChunk)
        .join(models.Document, models.DocumentChunk.document_id == models.Document.id)
        .filter(models.Document.user_id == user_id)
        .filter(models.DocumentChunk.embedding.isnot(None))
        .all()
    )

    if not chunks:
        return []

    # 2. Compute cosine similarity for each chunk
    query_vec = np.array(query_embedding, dtype=np.float32)
    norm_query = np.linalg.norm(query_vec)
    if norm_query == 0:
        return []

    scored_chunks = []
    for chunk in chunks:
        chunk_vec = np.array(chunk.embedding, dtype=np.float32)
        norm_chunk = np.linalg.norm(chunk_vec)
        if norm_chunk > 0:
            similarity = float(np.dot(query_vec, chunk_vec) / (norm_query * norm_chunk))
            scored_chunks.append((similarity, chunk))

    # 3. Sort by highest similarity first and take top K
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:limit]]

def create_conversation(db: Session, user_id: int, title: str = "New Conversation") -> models.Conversation:
    conv = models.Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

def get_user_conversations(db: Session, user_id: int) -> List[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.user_id == user_id)
        .order_by(models.Conversation.created_at.desc())
        .all()
    )

def get_user_conversation_by_id(db: Session, conversation_id: int, user_id: int) -> Optional[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.id == conversation_id, models.Conversation.user_id == user_id)
        .first()
    )

def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None
) -> models.Message:
    msg = models.Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def get_document_by_id_internal(db: Session, document_id: int) -> Optional[models.Document]:
    return db.query(models.Document).filter(models.Document.id == document_id).first()

