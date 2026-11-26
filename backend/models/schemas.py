"""Pydantic 스키마 — 요청·응답 검증."""
from datetime import date as date_type
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Skill = Literal["listening", "reading", "speaking", "vocabulary", "writing", "overall"]
FocusSkill = Literal["listening", "reading", "speaking", "vocabulary", "writing"]
Reaction = Literal["easy", "just_right", "hard"]
AgeBand = Literal["3-6", "7-12", "13-17", "18+"]
Level = Literal["L1", "L2", "L3", "L4", "L5", "L6"]
Confidence = Literal["high", "low"]


class RecordIn(BaseModel):
    """학습 기록: (date, value=학습분, memo) + 스킬/반응 + 카탈로그 연결."""

    date: str
    value: int = Field(gt=0, le=1440, description="학습 시간(분)")
    memo: str = Field(min_length=1, max_length=200, description="무엇을 했는지 (콘텐츠명 등)")
    skill: Optional[Skill] = None
    reaction: Optional[Reaction] = Field(default=None, description="쉬움/적정/어려움")
    content_id: Optional[str] = Field(
        default=None, max_length=80, description="카탈로그 콘텐츠 ID (추천 카드에서 기록 시)"
    )

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        try:
            d = date_type.fromisoformat(v)
        except ValueError as exc:
            raise ValueError("YYYY-MM-DD 형식이어야 합니다") from exc
        if d > date_type.today():
            raise ValueError("미래 날짜는 기록할 수 없습니다")
        return v

    @field_validator("memo")
    @classmethod
    def _strip_memo(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("내용을 입력해 주세요")
        return v


class ChatMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(default=None, max_length=80)
    history: list[ChatMsg] = Field(default_factory=list, max_length=100)


class ConversationIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    messages: list[ChatMsg] = Field(min_length=1)


class ProfileIn(BaseModel):
    """보낸 필드만 갱신한다. 값으로 null을 보내면 그 필드를 비운다."""

    age_band: Optional[AgeBand] = None
    level: Optional[Level] = None
    confidence: Optional[Confidence] = None
    goals: Optional[str] = Field(default=None, max_length=200)
    interests: Optional[str] = Field(default=None, max_length=200)
    focus_skill: Optional[FocusSkill] = None
    daily_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    prefer_free: Optional[bool] = None
