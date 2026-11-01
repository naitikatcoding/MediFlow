from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    facility_id: Optional[str] = Field(default=None, max_length=64)
    history: List[ChatTurn] = Field(default_factory=list, max_length=8)


class ChatSource(BaseModel):
    title: str
    source: str
    reference: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[ChatSource]
    retrieval_provider: Literal["meko", "yugabyte_pgvector", "local_sqlite"]
    answer_provider: Literal["gemini", "grounded_fallback"]
    generated_at: str
