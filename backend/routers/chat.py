"""AI 채팅 — 학습 요약·프로필 컨텍스트 주입 + 웹 검색 추천 + 대화 자동 저장."""
from datetime import datetime, timezone

from fastapi import APIRouter

from models.schemas import ChatIn
from services import ai, store
from services.analysis import build_summary

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
def chat(payload: ChatIn):
    profile = store.get_profile()
    summary = build_summary(store.list_records(), profile)
    reply, sources = ai.chat(
        payload.message, [m.model_dump() for m in payload.history], profile, summary
    )

    # 대화 자동 저장
    messages = [m.model_dump() for m in payload.history] + [
        {"role": "user", "content": payload.message},
        {"role": "assistant", "content": reply},
    ]
    first_user = next((m["content"] for m in messages if m["role"] == "user"), payload.message)
    title = first_user[:40] + ("…" if len(first_user) > 40 else "")
    cid = store.save_conversation(
        {
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": messages,
            "prompt_version": ai.PROMPT_VERSION,
        },
        payload.conversation_id,
    )
    return {"reply": reply, "sources": sources, "conversation_id": cid}
