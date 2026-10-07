# Enterprise Knowledge Assistant — Beginner Industry RAG Project

> A backend service where authenticated users can upload company documents (PDF, DOCX, TXT, MD) and ask questions in natural language. The system retrieves relevant chunks via semantic search + reranking and generates grounded answers with citations.

**Mental Model:** `UPLOAD → EXTRACT → CHUNK → EMBED → STORE → SEARCH → RERANK → ANSWER → CITE`

---

## Table of Contents
- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Database Design](#database-design)
- [API Endpoints](#api-endpoints)
- [Phase-wise Implementation (0-11)](#phase-wise-implementation-0-11)
- [Setup & Installation](#setup--installation)
- [Docker Setup](#docker-setup)
- [Environment Variables](#environment-variables)
- [Testing & Evaluation](#testing--evaluation)
- [Logging & Security](#logging--security)
- [Final Definition of Done](#final-definition-of-done)
- [Future Improvements](#future-improvements)

---

## Project Overview

Imagine a company has hundreds of PDFs — leave policies, product docs, FAQs, SOPs. Employees waste hours searching manually.

This project solves it:

1.  User registers/logs in (JWT auth).
2.  User uploads `Leave Policy.pdf`.
3.  System extracts text, cleans it, chunks it with metadata (page, section).
4.  Embeddings generated and stored in PostgreSQL + pgvector.
5.  User asks: "How many casual leaves can I take?"
6.  System does vector search → reranking → builds context → LLM answers only from retrieved content → returns answer with source citations.
7.  Chat history is preserved per user.

This is intentionally built **phase-by-phase** with working checkpoints, not as one giant task.

---

## Tech Stack

| Area | Technology | Reason |
| :--- | :--- | :--- |
| Language | Python 3.11+ | Main implementation |
| API Framework | FastAPI | Modern, fast, auto OpenAPI docs |
| Validation | Pydantic v2 | Request/response validation |
| Database | PostgreSQL 15+ | Production relational DB |
| Vector Search | pgvector | Embeddings inside Postgres |
| ORM | SQLAlchemy 2.0 | DB access |
| Auth | JWT (access + refresh), bcrypt | Industry standard auth |
| LLM | OpenAI API / compatible | Generation + Embeddings |
| Document Parsing | PyMuPDF, python-docx | PDF/DOCX/TXT/MD extraction |
| Reranker | Cross-Encoder (sentence-transformers) | Candidate reordering |
| Testing | Pytest + FastAPI TestClient | Unit + API tests |
| Container | Docker + Docker Compose | Repeatable setup |
| Logging | Python logging + Request ID middleware | Observability |

**Out of scope for beginner path:** Redis, Kafka, Kubernetes, microservices, advanced agent frameworks.

---

## System Architecture

```
User / Postman / Frontend
        |
        v
     FastAPI ( /api/v1/* )
     /      |      \
    /       |       \
 Auth   PostgreSQL + pgvector
  |         ^
  |         |
  v         |
RAG Service ----> LLM API (Embeddings + Chat)
  ^
  |
Document Ingestion Pipeline
  |
PDF/DOCX/TXT/MD -> Extract -> Clean -> Chunk -> Embed -> Store
```

**Two main flows:**

1.  **Document Flow:** Upload → validate (type/size) → save locally → status=UPLOADED → extract text → normalize → chunk (500-800 tokens, 80-120 overlap) → embedding → status=READY
2.  **Question Flow:** Authenticate → POST /chat → query embedding → pgvector top 8-12 → Cross-Encoder rerank → top 3-5 → prompt building (grounded) → LLM → answer + citations + save to conversation history

---

## Database Design

Minimal beginner-friendly design — every user-owned record is traceable to user_id (ownership rule).

### users
`id (UUID/PK), name, email (UNIQUE), password_hash, created_at, updated_at`

### documents
`id, user_id (FK), filename, file_path, file_type, file_size, status (UPLOADED/PROCESSING/READY/FAILED), created_at, updated_at`

### document_chunks
`id, document_id (FK), content, embedding (pgvector vector(1536)), page_number, section, chunk_index, token_count, created_at`
- Index: IVFFLAT / HNSW on embedding for cosine similarity

### conversations
`id, user_id (FK), title, created_at, updated_at`

### messages
`id, conversation_id (FK), role (user/assistant), content, sources (JSONB - citations), created_at`

Relationships: User 1→N Documents, Document 1→N Chunks, User 1→N Conversations, Conversation 1→N Messages

---

## API Endpoints

| Method | Endpoint | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET | /health | No | Service health `{"status":"ok"}` |
| GET | /api/v1/ping | No | Test endpoint |
| POST | /api/v1/echo | No | Echo JSON |
| POST | /api/v1/auth/register | No | Register new user |
| POST | /api/v1/auth/login | No | Login, returns access + refresh tokens |
| POST | /api/v1/auth/refresh | Yes | Refresh access token |
| GET | /api/v1/auth/me | Yes | Current user profile |
| POST | /api/v1/documents/upload | Yes | Upload PDF/DOCX/TXT/MD (multipart/form-data) |
| GET | /api/v1/documents | Yes | List own documents (paginated) |
| GET | /api/v1/documents/{id} | Yes | Get one document metadata |
| DELETE | /api/v1/documents/{id} | Yes | Delete doc + chunks |
| POST | /api/v1/chat | Yes | Ask RAG question, returns answer + sources |
| GET | /api/v1/conversations | Yes | List own conversations (paginated) |
| GET | /api/v1/conversations/{id} | Yes | Get chat history |

All protected endpoints expect: `Authorization: Bearer <access_token>`

Consistent error format:
```json
{
  "detail": "Error message",
  "code": "VALIDATION_ERROR",
  "request_id": "req_abc123"
}
```

---

## Phase-wise Implementation (0-11)

### Phase 0: Environment + Git Setup
**Outcome:** Clean project runs locally and is in Git.

**What I Did:**
- Created repo structure: `app/`, `app/main.py`, `app/config.py`, `tests/`, `scripts/`, `uploads/`
- Set up Python venv and `requirements.txt` / `pyproject.toml`
- Created `.env.example` and `.gitignore` (ignored `uploads/`, `.env`, `__pycache__`)
- Added initial README with install steps
- Verified `uvicorn app.main:app --reload` works

**Checkpoint Achieved:** Project runs, Git commits done, new dev can onboard from README.

### Phase 1: FastAPI Basics
**Outcome:** Working API before DB or AI logic.

**What I Did:**
- Built FastAPI app with routers
- Implemented `GET /health`, `GET /api/v1/ping`, `POST /api/v1/echo` with Pydantic models
- Learned HTTP methods, status codes, path vs query params
- Enabled Swagger at `/docs` and ReDoc at `/redoc`
- Added 3+ automated tests with `TestClient`

**Checkpoint Achieved:** All endpoints testable in Swagger UI, tests passing.

### Phase 2: PostgreSQL + Users
**Outcome:** App creates and reads users from real DB.

**What I Did:**
- Set up PostgreSQL + pgvector extension (`CREATE EXTENSION vector`)
- Created `users` table with SQLAlchemy models: id, name, email, password_hash, created_at
- Implemented `POST /api/v1/users` and `GET /api/v1/users/{id}`
- Added unique constraint on email with clean 400 error
- Understood why passwords are never plain text

**Checkpoint Achieved:** User created via API visible in DB, duplicate email returns validation error.

### Phase 3: Authentication with JWT
**Outcome:** Only authenticated users can access protected endpoints.

**What I Did:**
- Implemented password hashing with `bcrypt` / `passlib`
- Built `POST /api/v1/auth/register`, `/login`, `/refresh`, `/auth/me`
- Implemented access token (15 min) + refresh token (7 days) flow
- Created `get_current_user` dependency checking `Authorization: Bearer <token>`
- Ensured `password_hash` never returned in responses
- Tested 401 on protected endpoint without token

**Checkpoint Achieved:** Register → Login → token → /me works, unauthenticated requests blocked.

### Phase 4: Document Upload
**Outcome:** Authenticated users can upload and track document status.

**What I Did:**
- Designed `documents` table: id, user_id, filename, file_type, status (UPLOADED/PROCESSING/READY/FAILED)
- Implemented `POST /api/v1/documents/upload` with `multipart/form-data` validation
- Allowed types: PDF, DOCX, TXT, MD. Rejected others with 400
- Enforced max file size (e.g., 20MB) and user ownership (users see only own docs)
- Stored files locally in `uploads/{user_id}/{doc_id}/`
- Implemented list, get-by-id, delete endpoints with pagination
- On delete, cascade delete chunks and embeddings

**Checkpoint Achieved:** PDF upload → DB row → list filtered by user → delete removes access.

### Phase 5: Text Extraction + Chunking
**Outcome:** Document becomes clean, searchable chunks with metadata.

**What I Did:**
- Extraction: PyMuPDF for PDF (with page numbers), python-docx for DOCX, direct read for TXT/MD
- Normalization: Removed extra spaces, empty lines, fixed line breaks
- Chunking strategy: Structure-aware → split by headings/paragraphs → combine to 500-800 tokens → 80-120 token overlap → preserve sentence boundaries
- Stored metadata: document_id, content, page_number, section heading, chunk_index
- Saved to `document_chunks` table without embeddings yet

**Checkpoint Achieved:** Uploaded real policy doc, printed chunk count, manually inspected 5-10 chunks with correct document_id and source.

### Phase 6: Embeddings + Vector Search
**Outcome:** System finds semantically relevant chunks for a question.

**What I Did:**
- Integrated OpenAI `text-embedding-3-small` (1536 dim) to embed each chunk
- Stored vector in pgvector `embedding` column
- Created HNSW/IVFFLAT index: `CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops)`
- Built search function: question → embedding → cosine similarity search → top 5-8 chunks
- Tested with known question: "How many casual leaves?" → verified correct section in top results

**Checkpoint Achieved:** Basic semantic search works before adding reranking — proved retrieval layer is solid.

### Phase 7: First RAG Chatbot
**Outcome:** Answers from retrieved context, not model hallucination.

**What I Did:**
- Built `POST /api/v1/chat` endpoint: accepts `question` + optional `document_id` + `conversation_id`
- Pipeline: Retrieve top chunks → build grounded prompt → call LLM (gpt-4o-mini / gpt-3.5)
- Prompt rule: "Answer ONLY from supplied context. If not found, say information not found. Do not invent company-specific answers."
- Returned format: `{ answer, sources: [{document_id, filename, page, chunk_id, score}], conversation_id }`
- Saved Q&A to messages table

**Checkpoint Achieved:** Known questions answered correctly, unrelated questions return "not found" instead of hallucinating, response includes sources.

### Phase 8: Better Chunking + Reranking
**Outcome:** Retrieval quality improves without complex architecture.

**What I Did:**
- Improved chunking: Preserved headings, avoided mid-sentence cuts, avoided mixing unrelated sections, kept section title in each chunk
- Implemented two-step pipeline:
  1. Vector search → 8-12 candidates
  2. Cross-Encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) → re-scores query+chunk together → keep best 3-5
  3. Send only final chunks to LLM
- Created evaluation CSV to compare vector-only vs vector+reranker on 10-20 questions
- Logged latency and relevance improvement

**Checkpoint Achieved:** Correct chunk moved from rank 6 → rank 1 after reranking in evaluation.

### Phase 9: Citations + Chat History
**Outcome:** App is trustworthy and usable.

**What I Did:**
- Created `conversations` and `messages` tables
- Every grounded answer returns citations: `[1] Leave Policy.pdf - page 4`, `[2] HR Handbook.docx - section "Leave Rules"`
- Implemented `GET /api/v1/conversations` and `GET /api/v1/conversations/{id}` with ownership check
- Access control: Users can only read own conversations, only query own documents, backend verifies document_id ownership (never trust client)
- On app restart, history persists from DB

**Checkpoint Achieved:** 3 questions in a conversation → restart app → history still available, every answer has sources.

### Phase 10: Testing + RAG Evaluation
**Outcome:** Quality is measurable, not "it seems good".

**What I Did:**
- Software tests:
  - Auth tests: register, login, 401 cases
  - Document upload validation: wrong extension, too large, ownership
  - CRUD and access-control tests: user A cannot see user B docs
  - Chat endpoint tests
- RAG evaluation:
  - Created `eval_questions.csv` with 20 realistic questions + expected source doc/page
  - Script `scripts/evaluate.py` runs retrieval and records top-5
  - Metrics calculated:
    - **Hit@5 / Recall@5**: Did correct chunk appear in top 5?
    - **MRR**: How early did correct result appear?
    - **Answer Correctness**: Manual check
    - **Citation Correctness**: Does cited source support answer?
    - **Latency**: Avg retrieval + LLM time
  - Documented 5 failure cases and fixes (e.g., table parsing, acronym mismatch)

**Checkpoint Achieved:** Hit@5 and latency calculated, 5 failure improvements logged.

### Phase 11: Docker + Logging + Final Polish
**Outcome:** Deployable and presentable project.

**What I Did:**
- Docker:
  - `Dockerfile` for FastAPI app (python:3.11-slim, copy requirements, run uvicorn)
  - `docker-compose.yml` for API + PostgreSQL + pgvector
  - Env vars passed via `.env`
  - Volume for `uploads/` and pgdata
- Logging:
  - Request ID middleware (uuid per request, returned in header `X-Request-ID`)
  - Logs: endpoint, method, response time, status code, document processing status, retrieval count & latency
  - Never logging passwords, tokens, secrets
  - Structured JSON logging
- API Polish:
  - Consistent JSON error format
  - Pagination (`?page=1&limit=20`) for documents and conversations
  - Pydantic validation on all inputs
  - Proper HTTP status codes (201 for create, 401, 403, 404, 413, 422)
  - Full OpenAPI docs at `/docs`

**Checkpoint Achieved:** Cloned repo to clean folder → `docker-compose up` → register → upload → ask → cited answer works.

---

## Logging & Security

- Request ID middleware for tracing
- Logs include: request_id, user_id (if auth), endpoint, latency, retrieval stats
- Never logs: password_hash, raw JWT, OPENAI_API_KEY
- Security: bcrypt hashing, JWT auth, file type/size validation, ownership checks on every query, no trust on client document_id

---

## Final Definition of Done

- [x] User can register and login, protected endpoints reject unauth
- [x] Password stored only as secure hash
- [x] User can upload PDF/DOCX/TXT/MD, validation + size limit + ownership
- [x] Text extracted and chunked with page/section metadata
- [x] Embeddings stored in PostgreSQL + pgvector with index
- [x] Question retrieves relevant chunks (top 8-12 → rerank → top 3-5)
- [x] Reranking improves ordering
- [x] LLM produces grounded answer, says not found if context missing
- [x] Answer includes citations/sources
- [x] Chat history persisted, per-user isolation
- [x] Tests + evaluation metrics (Hit@5, MRR, latency)
- [x] Docker + logging + polished API docs

---

## Project Structure

```
Enterprise-Rag-Backend/
├── app/
│   ├── __init__.py
│   ├── chunking.py           # Text extraction, heading detection, and sentence chunker
│   ├── config.py             # App configurations, secrets, and environment loader
│   ├── crud.py               # Database CRUD logic and vector similarity queries
│   ├── database.py           # SQLAlchemy engine and session dependency
│   ├── embeddings.py         # Local FastEmbed vector generation service
│   ├── exceptions.py         # Standardized JSON error response handlers
│   ├── generator.py          # Google Gemini synthesis with anti-hallucination guardrails
│   ├── logging_config.py     # Request ID tracking, timing middleware, and log scrubbing
│   ├── main.py               # FastAPI application, route declarations, and lifecycle
│   ├── models.py             # SQLAlchemy models (User, Document, Chunk, Conversation, Message)
│   ├── reranker.py           # Cross-encoder candidate reranking pipeline
│   ├── schemas.py            # Pydantic request, response, and pagination models
│   ├── security.py           # Password hashing, JWT token creation, and auth dependencies
│   └── tasks.py              # Background worker for async document ingestion
├── test/
│   ├── __init__.py
│   └── test_main.py          # Automated Pytest suite (Auth, upload, CRUD, tenant isolation)
├── uploads/                  # Managed storage directory for uploaded files
├── .dockerignore
├── .env.example
├── .gitignore
├── check_db.py               # Diagnostic script for database verification
├── docker-compose.yml        # Multi-container orchestration (API + PostgreSQL)
├── Dockerfile                # Production container definition
├── eval_questions.csv        # 20-question RAG benchmark dataset
├── eval_results.csv          # Evaluation output logs (Hit@5, MRR, Latency)
├── evaluate_reranker.py      # Reranker comparative evaluation script
├── pyproject.toml            # Project configuration and Pytest settings
├── README.md                 # Complete documentation
├── requirements.txt          # Production and development dependencies
└── run_evaluation.py         # Benchmark harness runner

## Future Improvements
Frontend User Interface (UI)

Ek modern web interface (Next.js / React ya Streamlit) integrate karna jahan normal user direct drag-and-drop karke documents upload kar sake aur real-time chat interface mein citations dekh sake.

Hybrid Search (BM25 + Dense Vector Search)

Abhi search pure vector-based dense embeddings par chal rahi hai. BM25 (keyword search) aur vector search ko milakar Reciprocal Rank Fusion (RRF) lagana taaki specific policy codes, exact abbreviations aur acronyms aur behtar match ho sakein.

Advanced Table & Image Extraction (Multimodal RAG)

Policy documents ke complex tabular data aur flowchart images ko preserve karne ke liye OCR aur specialized markdown table parsers (jaise unstructured ya layout-aware parsers) ka use karna.

Query Expansion & Semantic Routing

User ke short ya confusing sawalon ko pehle LLM se expand/rephrase karwana (e.g., "WFH rules" ko "work from home / remote work policy guidelines" mein expand karna) taaki candidate retrieval 100% accurate rahe.

Asynchronous Background Workers (Celery / Redis)

Badi files (100+ pages PDF) ko process karne ke liye background task queue (Celery + Redis) implement karna taaki upload request instantly return ho aur heavy chunking background mein chalti rahe.

Streaming Responses (Server-Sent Events / WebSockets)

Assistant answers ke liye token-by-token streaming response dena taaki user ko pura answer generate hone tak wait na karna pade aur frontend par ChatGPT jaisa real-time typing effect mile.

Production Caching Layer

Repeat hone wale questions aur unke embeddings ko Redis cache mein save karna taaki duplicate queries ka answer 0ms database lookup aur zero LLM cost ke sath instant return ho jaye.
---

**Author:** Mohd Zaid 