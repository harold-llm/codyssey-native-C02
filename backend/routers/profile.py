"""학습자 프로필 (연령대·레벨·목표·관심사 등)."""
from fastapi import APIRouter

from models.schemas import ProfileIn
from services import store

router = APIRouter(prefix="/api/profile", tags=["profile"])

DEFAULTS = {
    "age_band": None,
    "level": None,
    "confidence": None,
    "goals": None,
    "interests": None,
    "focus_skill": None,
    "daily_minutes": None,
    "prefer_free": False,
}


@router.get("")
def get_profile():
    return {**DEFAULTS, **store.get_profile()}


@router.put("")
def update_profile(p: ProfileIn):
    # 보낸 필드만 갱신 (null을 보내면 비움). 빈 문자열은 null로 취급.
    fields = {
        k: (v.strip() or None) if isinstance(v, str) else v
        for k, v in p.model_dump(exclude_unset=True).items()
    }
    if fields.get("prefer_free") is None and "prefer_free" in fields:
        fields["prefer_free"] = False
    if not fields:
        return get_profile()
    return {**DEFAULTS, **store.set_profile(fields)}
