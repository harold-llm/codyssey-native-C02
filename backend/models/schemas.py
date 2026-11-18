"""Pydantic 스키마 — 요청 데이터 검증."""
from datetime import date as date_type
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Skill = Literal["listening", "reading", "speaking", "vocabulary", "overall"]
Reaction = Literal["easy", "just_right", "hard"]
AgeBand = Literal["3-6", "7-12", "13-17", "18+"]
Level = Literal["L1", "L2", "L3", "L4", "L5", "L6"]
Confidence = Literal["high", "low"]


class RecordIn(BaseModel):
    """학습 기록: (date, value=학습분, memo) + 스킬/반응."""

    date: str
    value: int = Field(gt=0, le=1440, description="학습 시간(분)")
    memo: str = Field(max_length=200, description="한 무엇을 (콘텐츠명 등)")
    skill: Optional[Skill] = None
    reaction: Optional[Reaction] = Field(default=None, description="쉬움/적정/어려움")

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        try:
            date_type.fromisoformat(v)
        except ValueError as exc:
            raise ValueError("YYYY-MM-DD 형식이어야 합니다") from exc
        return v


class ChatMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    history: list[ChatMsg] = Field(default_factory=list)


class ConversationIn(BaseModel):
    title: str = Field(max_length=80)
    messages: list[ChatMsg] = Field(min_length=1)


class ProfileIn(BaseModel):
    age_band: Optional[AgeBand] = None
    level: Optional[Level] = None
    confidence: Optional[Confidence] = None
    goals: Optional[str] = Field(default=None, max_length=200)
    daily_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
