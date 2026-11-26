"""큐레이션 카탈로그 — 로드·검증·조회 (Bloomy catalog 방식 계승, 전 연령으로 확장).

카탈로그는 추천의 1차 근거(RAG 코퍼스)다. 로드 시 필드를 엄격히 검증해
잘못된 항목이 조용히 추천되지 않게 한다.
"""
import json
from functools import lru_cache
from typing import Optional

from config import CATALOG_PATH

AGE_BANDS = ("3-6", "7-12", "13-17", "18+")
SKILLS = ("listening", "reading", "speaking", "vocabulary", "writing")
TYPES = ("video", "app", "book", "podcast", "website", "course", "tutor", "community", "tool")
COSTS = ("free", "freemium", "paid")

LEVELS = {
    1: ("L1", "초입문 (소리)", "노래·운율로 영어 소리와 리듬에 익숙해지는 단계"),
    2: ("L2", "기본 듣기", "짧은 지시·문장을 듣고 이해하는 단계"),
    3: ("L3", "짧은 문장", "짧은 문장을 따라 말하고 만들어 보는 단계"),
    4: ("L4", "기초 읽기", "그림 지원이 있는 쉬운 책을 읽는 단계"),
    5: ("L5", "쉬운 텍스트 독해", "짧은 기사·챕터북·일상 회화를 혼자 이해하는 단계"),
    6: ("L6", "실제 자료", "소설·뉴스·강의 등 원어민용 자료를 다루는 단계"),
}

AGE_BAND_KO = {"3-6": "3~6세", "7-12": "7~12세", "13-17": "13~17세", "18+": "성인"}
SKILL_KO = {
    "listening": "듣기", "reading": "읽기", "speaking": "말하기",
    "vocabulary": "어휘", "writing": "쓰기", "overall": "종합",
}
TYPE_KO = {
    "video": "영상", "app": "앱", "book": "책", "podcast": "팟캐스트", "website": "웹사이트",
    "course": "강좌", "tutor": "1:1 수업", "community": "커뮤니티", "tool": "도구",
}
COST_KO = {"free": "무료", "freemium": "부분 무료", "paid": "유료"}


class CatalogError(ValueError):
    """카탈로그 파일 형식 오류."""


def level_num(level: Optional[str]) -> Optional[int]:
    """'L3' → 3, None/잘못된 값 → None"""
    if not level or not isinstance(level, str) or not level.upper().startswith("L"):
        return None
    try:
        n = int(level[1:])
    except ValueError:
        return None
    return n if n in LEVELS else None


def level_label(n: int) -> str:
    code, name, _ = LEVELS[n]
    return f"{code} {name}"


def validate(items: object) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise CatalogError("items는 비어 있지 않은 배열이어야 합니다")
    seen: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            raise CatalogError("항목은 객체여야 합니다")
        iid = it.get("id")
        for key in ("id", "title", "provider", "link", "why", "how_to"):
            if not isinstance(it.get(key), str) or not it[key].strip():
                raise CatalogError(f"{iid}: '{key}' 필드가 비어 있습니다")
        if iid in seen:
            raise CatalogError(f"중복 id: {iid}")
        seen.add(iid)
        if not it["link"].startswith("https://"):
            raise CatalogError(f"{iid}: 링크는 https 여야 합니다")
        bands = it.get("age_bands")
        if not isinstance(bands, list) or not bands or any(b not in AGE_BANDS for b in bands):
            raise CatalogError(f"{iid}: age_bands 값이 올바르지 않습니다")
        lo, hi = it.get("level_min"), it.get("level_max")
        if type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi <= 6:
            raise CatalogError(f"{iid}: level_min/level_max는 1 ≤ min ≤ max ≤ 6")
        skills = it.get("skills")
        if not isinstance(skills, list) or not skills or any(s not in SKILLS for s in skills):
            raise CatalogError(f"{iid}: skills 값이 올바르지 않습니다")
        if it.get("type") not in TYPES:
            raise CatalogError(f"{iid}: type 값이 올바르지 않습니다")
        if it.get("cost") not in COSTS:
            raise CatalogError(f"{iid}: cost 값이 올바르지 않습니다")
        if it["cost"] != "free" and not str(it.get("price_note") or "").strip():
            raise CatalogError(f"{iid}: 유료/부분 무료 항목은 price_note가 필요합니다")
        if type(it.get("minutes")) is not int or not 1 <= it["minutes"] <= 120:
            raise CatalogError(f"{iid}: minutes는 1~120 정수")
        if not isinstance(it.get("tags", []), list):
            raise CatalogError(f"{iid}: tags는 배열이어야 합니다")
    return items


@lru_cache(maxsize=1)
def items() -> tuple[dict, ...]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("items") if isinstance(data, dict) else data
    return tuple(validate(raw))


def by_id() -> dict[str, dict]:
    return {it["id"]: it for it in items()}


def get(content_id: Optional[str]) -> Optional[dict]:
    if not content_id:
        return None
    return by_id().get(content_id)


def card(item: dict, reasons: Optional[list[str]] = None, score: Optional[float] = None) -> dict:
    """UI·API용 추천 카드 (카탈로그 항목 + 적합 이유)."""
    out = {
        "id": item["id"],
        "title": item["title"],
        "provider": item["provider"],
        "link": item["link"],
        "type": item["type"],
        "type_ko": TYPE_KO[item["type"]],
        "cost": item["cost"],
        "cost_ko": COST_KO[item["cost"]],
        "price_note": item.get("price_note"),
        "minutes": item["minutes"],
        "skills": list(item["skills"]),
        "levels": f"L{item['level_min']}" + (
            f"~L{item['level_max']}" if item["level_max"] != item["level_min"] else ""
        ),
        "age_bands": list(item["age_bands"]),
        "why": item["why"],
        "how_to": item["how_to"],
        "reasons": reasons or [],
    }
    if score is not None:
        out["score"] = round(score, 4)
    return out
