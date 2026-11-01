from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import answer_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def send_chat_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    """Answer an operational question using retrieved context and live inventory facts."""
    history = [turn.model_dump() for turn in payload.history]
    return answer_chat(
        db=db,
        question=payload.question,
        facility_id=payload.facility_id,
        history=history,
    )
