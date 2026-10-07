import os
import shutil
from typing import List
from app.generator import generate_rag_response
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.reranker import rerank_chunks
from app.database import engine, Base, get_db
from app import schemas, crud, models
from app import chunking
from app.embedding import get_embedding
from fastapi import Query
from fastapi.exceptions import RequestValidationError
from app.logging_config import RequestLoggingMiddleware, logger
from app.exceptions import custom_http_exception_handler, validation_exception_handler

from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)

# Automatically create all tables in PostgreSQL
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Enterprise Knowledge Assistant",
    version="1.0.0",
    description="Industry-style RAG backend service",
)

# --- Phase 1: Basics ---
class EchoRequest(BaseModel):
    message: str

class EchoResponse(BaseModel):
    message: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/v1/ping")
def ping():
    return {"ping": "pong"}

@app.post("/api/v1/echo", response_model=EchoResponse)
def echo(payload: EchoRequest):
    return {"message": payload.message}

# --- Phase 2: User Routes ---
@app.post(
    "/api/v1/users",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED
)
def create_new_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = crud.get_user_by_email(db, email=user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )
    return crud.create_user(db=db, user=user)

@app.get("/api/v1/users/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_id(db, user_id=user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    return db_user

# --- Phase 3: Auth Endpoints ---
@app.post(
    "/api/v1/auth/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = crud.get_user_by_email(db, email=user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )
    return crud.create_user(db=db, user=user)

@app.post("/api/v1/auth/login", response_model=schemas.TokenResponse)
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=credentials.email)
    if not user or not crud.verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

@app.post("/api/v1/auth/refresh", response_model=schemas.AccessTokenResponse)
def refresh_token(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)
    if token_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type for refresh."
        )
    
    user_id = token_data.get("sub")
    user = crud.get_user_by_id(db, user_id=int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found."
        )
    
    new_access_token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@app.get("/api/v1/auth/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# --- Phase 4 & 5: Document Handling & Chunking ---
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post(
    "/api/v1/documents/upload",
    response_model=schemas.DocumentResponse,
    status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    file_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{file.filename}")
    size = 0
    with open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                buffer.close()
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File exceeds maximum allowed size of 10MB."
                )
            buffer.write(chunk)

    # 1. Create document record with PROCESSING status
    doc = crud.create_document(
        db=db,
        user_id=current_user.id,
        filename=file.filename,
        file_type=ext.lstrip("."),
        status=models.DocumentStatus.PROCESSING
    )

    # 2. Phase 5: Extract and chunk
    raw_pages = chunking.extract_text_from_file(file_path, doc.file_type)
    chunks = chunking.create_chunks(raw_pages)
    
    # Checkpoint requirement: Print/log chunk count
    print(f"--> [Phase 5] Successfully extracted and created {len(chunks)} chunks for document_id={doc.id}")

    crud.store_document_chunks(db=db, document_id=doc.id, chunks=chunks)

    db.refresh(doc)
    return doc

@app.get("/api/v1/documents", response_model=List[schemas.DocumentResponse])
def list_documents(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_user_documents(db, user_id=current_user.id)

@app.get("/api/v1/documents/{document_id}", response_model=schemas.DocumentResponse)
def get_document(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = crud.get_user_document_by_id(db, document_id=document_id, user_id=current_user.id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )
    return doc

@app.get(
    "/api/v1/documents/{document_id}/chunks",
    response_model=List[schemas.ChunkResponse]
)
def get_document_chunks(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = crud.get_user_document_by_id(db, document_id=document_id, user_id=current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return crud.get_document_chunks(db, document_id=document_id)

@app.delete("/api/v1/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = crud.get_user_document_by_id(db, document_id=document_id, user_id=current_user.id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )
    
    file_path = os.path.join(UPLOAD_DIR, f"{current_user.id}_{doc.filename}")
    if os.path.exists(file_path):
        os.remove(file_path)

    crud.delete_user_document(db, document_id=document_id, user_id=current_user.id)
    return None

# --- Phase 6: Vector Search Endpoint ---

@app.post("/api/v1/search", response_model=List[schemas.SearchResultItem])
def search_chunks(
    payload: schemas.SearchRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty."
        )

    # 1. Convert query to vector locally
    query_vector = get_embedding(payload.query)

    # 2. Retrieve top-k closest chunks using cosine distance
    results = crud.search_similar_chunks(
        db=db,
        query_embedding=query_vector,
        user_id=current_user.id,
        limit=payload.top_k
    )

    return [
        schemas.SearchResultItem(
            chunk_id=c.id,
            document_id=c.document_id,
            chunk_index=c.chunk_index,
            content=c.content,
            page_number=c.page_number,
            section=c.section
        )
        for c in results
    ]

# --- Phase 7: RAG Query Endpoint ---

@app.post("/api/v1/query", response_model=schemas.QueryResponse)
def query_knowledge_base(
    payload: schemas.QueryRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty."
        )

    # Step 1: Candidate retrieval via vector similarity (fetch 10 candidates)
    query_vector = get_embedding(payload.query)
    candidate_chunks = crud.search_similar_chunks(
        db=db,
        query_embedding=query_vector,
        user_id=current_user.id,
        limit=10  # Broad candidate pool
    )

    if not candidate_chunks:
        return schemas.QueryResponse(
            query=payload.query,
            answer="I cannot find the answer to this question in your uploaded documents.",
            sources=[]
        )

    # Step 2: Rerank candidates with Cross-Encoder (keep best top_k, default 3-4)
    reranked_results = rerank_chunks(
        query=payload.query,
        chunks=candidate_chunks,
        top_k=payload.top_k
    )

    top_chunks = [chunk for chunk, score in reranked_results]

    # Step 3: LLM generation using only the reranked top chunks
    llm_answer = generate_rag_response(
        query=payload.query,
        context_chunks=top_chunks
    )

    # Step 4: Include sources with rerank scores
    citations = [
        schemas.Citation(
            chunk_id=c.id,
            document_id=c.document_id,
            page_number=c.page_number,
            section=c.section,
            content_snippet=c.content[:200] + ("..." if len(c.content) > 200 else ""),
            rerank_score=round(score, 4)
        )
        for c, score in reranked_results
    ]

    return schemas.QueryResponse(
        query=payload.query,
        answer=llm_answer,
        sources=citations
    )

# --- Phase 9: Conversation & Chat History Endpoints ---

@app.post("/api/v1/conversations", response_model=schemas.ConversationResponse, status_code=status.HTTP_201_CREATED)
def start_conversation(
    payload: schemas.ConversationCreate = schemas.ConversationCreate(),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.create_conversation(db=db, user_id=current_user.id, title=payload.title or "New Conversation")

@app.get("/api/v1/conversations", response_model=List[schemas.ConversationResponse])
def list_conversations(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_user_conversations(db=db, user_id=current_user.id)

@app.get("/api/v1/conversations/{conversation_id}", response_model=schemas.ConversationDetailResponse)
def get_conversation_history(
    conversation_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = crud.get_user_conversation_by_id(db=db, conversation_id=conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv

@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=schemas.MessageResponse)
def send_chat_message(
    conversation_id: int,
    payload: schemas.ChatQueryRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Enforce access control: verify conversation belongs to user
    conv = crud.get_user_conversation_by_id(db=db, conversation_id=conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # 2. Record User message in database
    crud.add_message(db=db, conversation_id=conv.id, role="user", content=query_text)

    # 3. Two-step retrieval: Candidate pool -> Cross-Encoder rerank
    query_vector = get_embedding(query_text)
    candidate_chunks = crud.search_similar_chunks(
        db=db,
        query_embedding=query_vector,
        user_id=current_user.id,
        limit=10
    )

    if not candidate_chunks:
        bot_msg = crud.add_message(
            db=db,
            conversation_id=conv.id,
            role="assistant",
            content="I cannot find the answer to this question in your uploaded documents.",
            sources=[]
        )
        return bot_msg

    reranked = rerank_chunks(query=query_text, chunks=candidate_chunks, top_k=payload.top_k)
    top_chunks = [chunk for chunk, _ in reranked]

    # 4. Generate grounded LLM response
    raw_answer = generate_rag_response(query=query_text, context_chunks=top_chunks)

    # 5. Format citations & lookup verified document names
    structured_sources = []
    formatted_source_lines = []

    for idx, chunk in enumerate(top_chunks, 1):
        doc = crud.get_document_by_id_internal(db, chunk.document_id)
        doc_name = doc.filename if doc else f"Document #{chunk.document_id}"
        
        # Build source description line
        parts = []
        if chunk.page_number:
            parts.append(f"page {chunk.page_number}")
        if chunk.section and chunk.section != f"Page {chunk.page_number}":
            parts.append(f'section "{chunk.section}"')
        location = " - " + ", ".join(parts) if parts else ""
        
        formatted_source_lines.append(f"[{idx}] {doc_name}{location}")
        
        structured_sources.append({
            "document_name": doc_name,
            "page_number": chunk.page_number,
            "section": chunk.section,
            "chunk_id": chunk.id
        })

    # Assemble final message content matching specification
    final_content = f"{raw_answer.strip()}\n\nSources:\n" + "\n".join(formatted_source_lines)

    # 6. Save Assistant response with citations in DB
    assistant_msg = crud.add_message(
        db=db,
        conversation_id=conv.id,
        role="assistant",
        content=final_content,
        sources=structured_sources
    )

    return assistant_msg

# Add Middleware
app.add_middleware(RequestLoggingMiddleware)

# Add Exception Handlers
app.add_exception_handler(HTTPException, custom_http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# --- Paginated Document List ---
@app.get("/api/v1/documents", response_model=schemas.PaginatedResponse[schemas.DocumentResponse])
def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * page_size
    query = db.query(models.Document).filter(models.Document.user_id == current_user.id)
    total = query.count()
    items = query.order_by(models.Document.created_at.desc()).offset(offset).limit(page_size).all()

    return schemas.PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )

# --- Paginated Conversations List ---
@app.get("/api/v1/conversations", response_model=schemas.PaginatedResponse[schemas.ConversationResponse])
def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * page_size
    query = db.query(models.Conversation).filter(models.Conversation.user_id == current_user.id)
    total = query.count()
    items = query.order_by(models.Conversation.created_at.desc()).offset(offset).limit(page_size).all()

    return schemas.PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )