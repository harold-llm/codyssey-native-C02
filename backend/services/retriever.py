"""로컬 RAG 검색 — 카탈로그 TF-IDF + 프로필 필터 + 학습 반응 재정렬.

Bloomy-AI `rag/retriever.py`의 결정적(deterministic) 희소 벡터 검색을 계승했다.
API·모델 다운로드 없이 동작하므로 키가 없어도 추천이 가능하고, LLM 모드에서는
이 결과가 "검수된 후보"로 프롬프트에 주입되어 추천의 근거가 된다.

점수 = 질의 유사도(TF-IDF 코사인) + 레벨 적합 + 목표 스킬 + 시간 적합 + 반응 이력
모든 가산·감산은 사람이 읽을 수 있는 이유(reasons)로 함께 반환한다.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from services import catalog
from services.catalog import AGE_BAND_KO, COST_KO, SKILL_KO, level_label, level_num

# 한국어 학습 용어 → 카탈로그 공통 토큰
ALIASES = {
    "리스닝": "listening", "듣기": "listening", "청취": "listening", "흘려듣기": "listening",
    "리딩": "reading", "읽기": "reading", "독해": "reading", "원서": "reading 원서",
    "스피킹": "speaking", "말하기": "speaking", "회화": "speaking 회화", "발음": "speaking 발음",
    "보카": "vocabulary", "어휘": "vocabulary", "단어": "vocabulary 단어",
    "라이팅": "writing", "쓰기": "writing", "영작": "writing 영작",
}
SKILL_WORDS = {
    "listening": ("listening",),
    "reading": ("reading",),
    "speaking": ("speaking",),
    "vocabulary": ("vocabulary",),
    "writing": ("writing",),
}
FREE_WORDS = ("무료", "공짜", "free", "돈 안", "비용 없")


def tokens(text: str) -> list[str]:
    text = (text or "").casefold()
    for key, value in ALIASES.items():
        text = text.replace(key, f" {value} ")
    words = re.findall(r"[a-z0-9]+|[가-힣]+", text)
    # 한국어는 조사가 붙으므로 2-gram을 함께 쓴다 (예: '그림책을' ↔ '그림책')
    grams = [w[i:i + 2] for w in words if re.search(r"[가-힣]", w) for i in range(len(w) - 1)]
    return words + grams


def _doc_text(it: dict) -> str:
    return " ".join([
        it["title"], it["provider"], it["why"], it["how_to"], " ".join(it.get("tags", [])),
        " ".join(it["skills"]), it["type"], catalog.TYPE_KO[it["type"]],
    ])


@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, Counter], dict[str, float]]:
    vectors = {it["id"]: Counter(tokens(_doc_text(it))) for it in catalog.items()}
    df = Counter(t for v in vectors.values() for t in v)
    n = len(vectors)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    return vectors, idf


def _cosine(q: Counter, v: Counter, idf: dict[str, float]) -> float:
    def w(vec: Counter, t: str) -> float:
        return vec[t] * idf.get(t, 1.0)

    num = sum(w(q, t) * w(v, t) for t in q.keys() & v.keys())
    den = math.sqrt(sum(w(q, t) ** 2 for t in q)) * math.sqrt(sum(w(v, t) ** 2 for t in v))
    return num / den if den else 0.0


def detect_skill(text: str) -> Optional[str]:
    toks = set(tokens(text))
    for skill, words in SKILL_WORDS.items():
        if any(w in toks for w in words):
            return skill
    return None


def wants_free(text: str) -> bool:
    t = (text or "").casefold()
    return any(w in t for w in FREE_WORDS)


# 연령대별 레벨 미판정 시 출발 가정 (기획서 5.2 연령대별 자연 범위)
DEFAULT_LEVEL_BY_AGE = {"3-6": 1, "7-12": 3, "13-17": 4, "18+": 4}


@dataclass
class Query:
    text: str = ""
    age_band: Optional[str] = None
    level: Optional[int] = None
    skill: Optional[str] = None
    daily_minutes: Optional[int] = None
    free_only: bool = False
    top_k: int = 3
    exclude_ids: set[str] = field(default_factory=set)


def query_from_profile(profile: dict, text: str = "", skill: Optional[str] = None,
                       free_only: Optional[bool] = None, top_k: int = 3) -> Query:
    goal_text = " ".join(x for x in (text, profile.get("goals") or "", profile.get("interests") or "") if x)
    return Query(
        text=goal_text,
        age_band=profile.get("age_band"),
        level=level_num(profile.get("level")),
        skill=skill or detect_skill(text) or profile.get("focus_skill"),
        daily_minutes=profile.get("daily_minutes") or None,
        free_only=bool(profile.get("prefer_free")) if free_only is None else free_only,
        top_k=top_k,
    )


def search(q: Query, summary: Optional[dict] = None) -> list[dict]:
    """조건에 맞는 카탈로그 후보를 점수순으로 반환. 각 hit: {item, score, reasons}."""
    vectors, idf = _index()
    qv = Counter(tokens(q.text))
    summary = summary or {}
    preferred = set(summary.get("preferred_content_ids") or ())
    struggling = set(summary.get("struggling_content_ids") or ())
    too_easy = set(summary.get("too_easy_content_ids") or ())
    signal = (summary.get("level_signal") or {}).get("direction")

    level = q.level or (DEFAULT_LEVEL_BY_AGE.get(q.age_band) if q.age_band else None)
    # 레벨 재점검 신호가 있으면 탐색 중심을 한 칸 옮긴다 (프로필은 바꾸지 않음)
    if level and signal == "up":
        level = min(6, level + 1)
    elif level and signal == "down":
        level = max(1, level - 1)

    hits = []
    for it in catalog.items():
        if it["id"] in q.exclude_ids:
            continue
        if q.age_band and q.age_band not in it["age_bands"]:
            continue
        if q.free_only and it["cost"] == "paid":
            continue
        reasons: list[str] = []
        score = _cosine(qv, vectors[it["id"]], idf) if qv else 0.0

        if level:
            lo, hi = it["level_min"], it["level_max"]
            if lo <= level <= hi:
                score += 0.6
                reasons.append(f"{level_label(level)} 수준에 맞음 (L{lo}~L{hi})" if lo != hi
                               else f"{level_label(level)} 수준에 맞음")
            elif lo == level + 1:
                score += 0.1
                reasons.append(f"한 단계 위(L{lo}) 도전 자료")
            elif hi == level - 1:
                score += 0.05
                reasons.append(f"한 단계 쉬운(L{hi}) 복습 자료")
            else:
                continue  # 두 단계 이상 차이는 제외

        if q.skill and q.skill in it["skills"]:
            score += 0.8
            reasons.append(f"목표 스킬 '{SKILL_KO[q.skill]}'과(와) 직접 연결")

        if q.daily_minutes:
            if it["minutes"] <= q.daily_minutes:
                score += 0.15
                reasons.append(f"하루 {q.daily_minutes}분 안에 가능 (1회 약 {it['minutes']}분)")
            elif it["minutes"] > q.daily_minutes * 1.5:
                score -= 0.3

        if it["cost"] == "free":
            score += 0.05
            if q.free_only:
                reasons.append("무료")

        cid = it["id"]
        if cid in preferred:
            score += 0.35
            reasons.append("최근 '적정' 반응이 이어진 자료 — 계속하기 좋아요")
        if cid in struggling:
            score -= 0.6
            reasons.append("최근 '어려움' 반응이 반복됨 — 쉬운 자료와 번갈아 하세요")
        if cid in too_easy:
            score -= 0.4

        hits.append({"item": it, "score": score, "reasons": reasons})

    hits.sort(key=lambda h: (-h["score"], h["item"]["id"]))
    return _diversify(hits, q.top_k)


def _diversify(hits: list[dict], k: int) -> list[dict]:
    """같은 제공처·같은 유형만 몰리지 않게 고른다 (가벼운 MMR)."""
    picked: list[dict] = []
    providers: set[str] = set()
    types: Counter = Counter()
    for h in hits:
        it = h["item"]
        brand = it["provider"].split(" ")[0]
        if brand in providers or types[it["type"]] >= 2:
            continue
        picked.append(h)
        providers.add(brand)
        types[it["type"]] += 1
        if len(picked) >= k:
            return picked
    for h in hits:  # 다양성 조건으로 모자라면 점수순으로 채운다
        if len(picked) >= k:
            break
        if h not in picked:
            picked.append(h)
    return picked


def to_cards(hits: list[dict]) -> list[dict]:
    return [catalog.card(h["item"], h["reasons"], h["score"]) for h in hits]


def candidates_text(hits: list[dict]) -> str:
    """시스템 프롬프트에 넣을 후보 목록 (근거 데이터)."""
    if not hits:
        return "(조건에 맞는 카탈로그 후보 없음 — 웹 검색과 일반 지식으로 보완하세요)"
    lines = []
    for i, h in enumerate(hits, 1):
        it = h["item"]
        price = COST_KO[it["cost"]] + (f" ({it['price_note']})" if it.get("price_note") else "")
        bands = ", ".join(AGE_BAND_KO[b] for b in it["age_bands"])
        lines.append(
            f"{i}. [{it['id']}] {it['title']} — {catalog.TYPE_KO[it['type']]} · {price} · 1회 약 {it['minutes']}분 · "
            f"L{it['level_min']}~L{it['level_max']} · {bands}\n"
            f"   링크: {it['link']}\n"
            f"   특징: {it['why']}\n"
            f"   사용법: {it['how_to']}\n"
            f"   적합 근거: {'; '.join(h['reasons']) or '질의와 관련'}"
        )
    return "\n".join(lines)
