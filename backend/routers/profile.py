"""학습자 프로필 (레벨·연령대·목표 등)."""
from fastapi import APIRouter

from models.schemas import ProfileIn
from services import store

router = APIRouter(prefix="/api/profile", tags=["profile"])

DEFAULTS = {
    "age_band": None,
    "level": None,
    "confidence": None,
    "goals": None,
    "daily_minutes": None,
}


@router.get("")
def get_profile():
    return {**DEFAULTS, **store.get_profile()}


@router.put("")
def update_profile(p: ProfileIn):
    fields = p.model_dump(exclude_none=True)
    if not fields:
        return get_profile()
    return {**DEFAULTS, **store.set_profile(fields)}
