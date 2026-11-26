"""카탈로그 조회 + 프로필 기반 추천 (LLM 없이 즉시, 비용 0)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services import catalog, retriever, store
from services.analysis import build_summary

router = APIRouter(prefix="/api", tags=["catalog"])

SkillParam = Optional[str]


def _check_skill(skill: SkillParam) -> Optional[str]:
    if skill and skill not in catalog.SKILLS:
        raise HTTPException(422, f"skill은 {', '.join(catalog.SKILLS)} 중 하나여야 합니다")
    return skill or None


@router.get("/catalog")
def list_catalog(
    age_band: Optional[str] = Query(None, description="3-6 | 7-12 | 13-17 | 18+"),
    level: Optional[str] = Query(None, description="L1~L6"),
    skill: SkillParam = None,
    cost: Optional[str] = Query(None, description="free | freemium | paid"),
):
    """카탈로그 전체 또는 조건 필터 (연령대·레벨 범위·스킬·비용)."""
    skill = _check_skill(skill)
    n = catalog.level_num(level)
    out = []
    for it in catalog.items():
        if age_band and age_band not in it["age_bands"]:
            continue
        if n and not it["level_min"] <= n <= it["level_max"]:
            continue
        if skill and skill not in it["skills"]:
            continue
        if cost and it["cost"] != cost:
            continue
        out.append(catalog.card(it))
    return {"count": len(out), "items": out}


@router.get("/catalog/{content_id}")
def get_catalog_item(content_id: str):
    it = catalog.get(content_id)
    if not it:
        raise HTTPException(404, "존재하지 않는 콘텐츠입니다")
    return catalog.card(it)


@router.get("/recommendations")
def recommendations(
    skill: SkillParam = None,
    q: str = Query("", max_length=200, description="추가 키워드 (예: 뉴스, 그림책)"),
    free_only: Optional[bool] = None,
    limit: int = Query(6, ge=1, le=12),
):
    """현재 프로필·학습 기록으로 카탈로그 추천 (적합 이유 포함)."""
    skill = _check_skill(skill)
    profile = store.get_profile()
    summary = build_summary(store.list_records(), profile)
    query = retriever.query_from_profile(profile, text=q, skill=skill, free_only=free_only, top_k=limit)
    hits = retriever.search(query, summary)
    return {
        "profile_ready": bool(profile.get("age_band")),
        "level_signal": summary.get("level_signal"),
        "items": retriever.to_cards(hits),
    }
