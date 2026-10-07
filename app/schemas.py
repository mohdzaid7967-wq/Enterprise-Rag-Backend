from app.models import DocumentStatus
from typing import Optional, List, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr 

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class DocumentResponse(BaseModel):
    id: int
    user_id: int
    filename: str
    file_type: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChunkResponse(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    content: str
    page_number: Optional[int]
    section: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

class SearchResultItem(BaseModel):
    chunk_id: int
    document_id: int
    chunk_index: int
    content: str
    page_number: Optional[int]
    section: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class Citation(BaseModel):
    chunk_id: int
    document_id: int
    page_number: Optional[int]
    section: Optional[str]
    content_snippet: str
    rerank_score: Optional[float] = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = 4

class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[Citation]

class MessageSource(BaseModel):
    document_name: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_id: int

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sources: Optional[List[MessageSource]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"

class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse] = []

class ChatQueryRequest(BaseModel):
    query: str
    top_k: int = 4

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: List[T]