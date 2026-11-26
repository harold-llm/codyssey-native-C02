"""AI 채팅 — 에이전트 실행 + 대화 자동 저장."""
from fastapi import APIRouter

from models.schemas import ChatIn
from services import agent, store

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _title(text: str) -> str:
    text = " ".join(text.split())
    return text[:40] + ("…" if len(text) > 40 else "")


@router.post("")
def chat(payload: ChatIn):
    history = [m.model_dump() for m in payload.history]
    result = agent.respond(payload.message, history, store.get_profile(), store.list_records())

    # 대화 자동 저장 — 기존 대화의 메시지(출처·추천 카드 포함)를 보존하며 이어 붙인다
    previous = store.get_conversation(payload.conversation_id) if payload.conversation_id else None
    messages = list(previous["messages"]) if previous and previous.get("messages") else history
    messages = messages + [
        {"role": "user", "content": payload.message},
        {
            "role": "assistant",
            "content": result.reply,
            "sources": result.sources,
            "recommendations": result.recommendations,
            "mode": result.mode,
            "intent": result.intent,
        },
    ]
    first_user = next((m["content"] for m in messages if m["role"] == "user"), payload.message)
    cid = store.save_conversation(
        {
            "title": (previous or {}).get("title") or _title(first_user),
            "messages": messages,
            "prompt_version": result.prompt_version,
        },
        payload.conversation_id,
    )
    return {**result.to_dict(), "conversation_id": cid}
