"""대화 기록 저장·조회·삭제."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from models.schemas import ConversationIn
from services import store

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", status_code=201)
def create_conversation(conv: ConversationIn):
    cid = store.save_conversation(
        {
            "title": conv.title,
            "created_at": _now(),
            "messages": [m.model_dump() for m in conv.messages],
        }
    )
    return {"id": cid, "title": conv.title}


@router.get("")
def list_conversations():
    return store.list_conversations()


@router.get("/{cid}")
def get_conversation(cid: str):
    c = store.get_conversation(cid)
    if not c:
        raise HTTPException(404, "존재하지 않는 대화입니다")
    return c


@router.delete("/{cid}")
def delete_conversation(cid: str):
    if not store.delete_conversation(cid):
        raise HTTPException(404, "존재하지 않는 대화입니다")
    return {"ok": True}
