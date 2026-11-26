"""학습 기록 요약 — 프롬프트 주입(컨텍스트 주입), 추천 재정렬, UI 요약 화면에 사용.

진단·평가가 아니라 '다음에 무엇을 권할지'를 위한 재현 가능한 계산만 한다.
(Bloomy memory.summary 원칙 계승)
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from services.catalog import SKILL_KO, level_num

CALIBRATION_WINDOW = 10   # 최근 N개 반응 기록
CALIBRATION_THRESHOLD = 7  # 그중 같은 반응이 M개 이상이면 레벨 재점검 제안


def _d(v: str) -> date:
    return date.fromisoformat(v)


def _empty(profile: dict, today: date) -> dict:
    return {
        "as_of": today.isoformat(),
        "period": None,
        "count": 0,
        "metrics": {
            "total": 0, "per_session": 0, "per_active_day": 0,
            "max": 0, "min": 0, "active_days": 0,
        },
        "trend": "기록 없음",
        "streak": 0,
        "last_7_days": 0,
        "goal": _goal(profile, 0),
        "skill_distribution": {},
        "reaction": {"easy": 0, "just_right": 0, "hard": 0},
        "level_signal": None,
        "content_responses": [],
        "preferred_content_ids": [],
        "struggling_content_ids": [],
        "too_easy_content_ids": [],
        "recent_days": [
            {"date": (today - timedelta(days=i)).isoformat(), "minutes": 0}
            for i in range(13, -1, -1)
        ],
        "level": profile.get("level"),
    }


def _goal(profile: dict, last_7: int) -> Optional[dict]:
    daily = profile.get("daily_minutes")
    if not daily:
        return None
    target = daily * 7
    return {
        "daily_minutes": daily,
        "weekly_target": target,
        "last_7_days": last_7,
        "percent": round(last_7 / target * 100) if target else 0,
    }


def level_signal(records: list[dict], level: Optional[str]) -> Optional[dict]:
    """최근 10개 반응 중 7개 이상이 '쉬움'/'어려움'이면 재점검을 제안 (자동 변경 없음)."""
    reacted = sorted(
        (r for r in records if r.get("reaction")),
        key=lambda r: (r.get("date", ""), r.get("created_at", "")),
        reverse=True,
    )[:CALIBRATION_WINDOW]
    if len(reacted) < CALIBRATION_THRESHOLD:
        return None
    easy = sum(1 for r in reacted if r["reaction"] == "easy")
    hard = sum(1 for r in reacted if r["reaction"] == "hard")
    n = level_num(level)
    if easy >= CALIBRATION_THRESHOLD:
        target = f"L{n + 1}" if n and n < 6 else None
        return {
            "direction": "up",
            "basis": f"최근 {len(reacted)}개 기록 중 '쉬움' {easy}개",
            "suggested_level": target,
            "message": "최근 학습이 쉽게 느껴지고 있어요. 한 단계 위 콘텐츠를 시도해 볼 때일 수 있어요.",
        }
    if hard >= CALIBRATION_THRESHOLD:
        target = f"L{n - 1}" if n and n > 1 else None
        return {
            "direction": "down",
            "basis": f"최근 {len(reacted)}개 기록 중 '어려움' {hard}개",
            "suggested_level": target,
            "message": "최근 학습이 버겁게 느껴지고 있어요. 한 단계 쉬운 콘텐츠로 리듬을 되찾아도 좋아요.",
        }
    return None


def _content_responses(records: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("content_id"):
            groups[r["content_id"]].append(r)
    out = []
    for cid, rows in sorted(groups.items()):
        counts = {"easy": 0, "just_right": 0, "hard": 0}
        for r in rows:
            if r.get("reaction") in counts:
                counts[r["reaction"]] += 1
        out.append({
            "content_id": cid,
            "sessions": len(rows),
            "minutes": sum(r["value"] for r in rows),
            "last_date": max(r["date"] for r in rows),
            **counts,
        })
    return out


def build_summary(
    records: list[dict], profile: Optional[dict] = None, today: Optional[date] = None
) -> dict:
    profile = profile or {}
    today = today or date.today()
    if not records:
        return _empty(profile, today)

    values = [r["value"] for r in records]
    dates = [_d(r["date"]) for r in records]
    latest, oldest = max(dates), min(dates)
    active = set(dates)

    # 추세: 오늘 기준 최근 14일 vs 직전 14일 총량
    r_start = today - timedelta(days=13)
    p_start = today - timedelta(days=27)
    recent = sum(r["value"] for r in records if _d(r["date"]) >= r_start)
    prev = sum(r["value"] for r in records if p_start <= _d(r["date"]) < r_start)
    if oldest > r_start - timedelta(days=1) and not prev:
        trend = "기록 초기 (2주 이상 쌓이면 추세를 보여 드려요)"
    elif prev == 0:
        trend = "상승 (직전 2주 기록 없음)" if recent else "쉬는 중 (최근 4주 기록 없음)"
    else:
        pct = (recent - prev) / prev * 100
        if pct >= 10:
            trend = f"상승 (+{pct:.0f}%)"
        elif pct <= -10:
            trend = f"하락 ({pct:.0f}%)"
        else:
            trend = f"유지 ({pct:+.0f}%)"

    skill_dist: dict[str, int] = {}
    for r in records:
        key = r.get("skill") or "overall"
        skill_dist[key] = skill_dist.get(key, 0) + r["value"]

    reaction = {"easy": 0, "just_right": 0, "hard": 0}
    for r in records:
        if r.get("reaction") in reaction:
            reaction[r["reaction"]] += 1

    # 연속 기록일: 오늘 기록이 아직 없으면 어제부터 센다
    d = today if today in active else today - timedelta(days=1)
    streak = 0
    while d in active:
        streak += 1
        d -= timedelta(days=1)

    by_day: dict[str, int] = defaultdict(int)
    for r in records:
        by_day[r["date"]] += r["value"]
    recent_days = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "minutes": by_day.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(13, -1, -1)
    ]
    last_7 = sum(x["minutes"] for x in recent_days[-7:])

    content = _content_responses(records)
    preferred = [c["content_id"] for c in content if c["just_right"] >= 2 and c["hard"] < c["just_right"]]
    struggling = [c["content_id"] for c in content if c["hard"] >= 2 and c["hard"] > c["just_right"]]
    too_easy = [c["content_id"] for c in content if c["easy"] >= 2 and c["easy"] > c["just_right"]]

    return {
        "as_of": today.isoformat(),
        "period": f"{oldest.isoformat()} ~ {latest.isoformat()}",
        "count": len(records),
        "metrics": {
            "total": sum(values),
            "per_session": round(sum(values) / len(values)),
            "per_active_day": round(sum(values) / len(active)),
            "max": max(values),
            "min": min(values),
            "active_days": len(active),
        },
        "trend": trend,
        "streak": streak,
        "last_7_days": last_7,
        "goal": _goal(profile, last_7),
        "skill_distribution": skill_dist,
        "reaction": reaction,
        "level_signal": level_signal(records, profile.get("level")),
        "content_responses": content,
        "preferred_content_ids": preferred,
        "struggling_content_ids": struggling,
        "too_easy_content_ids": too_easy,
        "recent_days": recent_days,
        "level": profile.get("level"),
    }


def summary_text(summary: dict) -> str:
    """요약을 시스템 프롬프트에 넣을 텍스트로 변환."""
    if not summary["count"]:
        return "아직 학습 기록이 없습니다."
    m = summary["metrics"]
    lines = [
        f"- 기간: {summary['period']} ({summary['count']}개 기록, 학습한 날 {m['active_days']}일, 현재 {summary['streak']}일 연속)",
        f"- 총 학습량: {m['total']}분 (학습한 날 평균 {m['per_active_day']}분, 1회 평균 {m['per_session']}분)",
        f"- 최근 7일: {summary['last_7_days']}분 · 최근 추세: {summary['trend']}",
    ]
    goal = summary.get("goal")
    if goal:
        lines.append(f"- 주간 목표 달성: {goal['last_7_days']}/{goal['weekly_target']}분 ({goal['percent']}%)")
    if summary["skill_distribution"]:
        total = sum(summary["skill_distribution"].values()) or 1
        parts = [
            f"{SKILL_KO.get(k, k)} {round(v / total * 100)}%"
            for k, v in sorted(summary["skill_distribution"].items(), key=lambda x: -x[1])
        ]
        lines.append(f"- 스킬 분포: {' / '.join(parts)}")
    r = summary["reaction"]
    lines.append(f"- 반응: 쉬움 {r['easy']} / 적정 {r['just_right']} / 어려움 {r['hard']}")
    sig = summary.get("level_signal")
    if sig:
        lines.append(f"- 레벨 재점검 신호: {sig['basis']} → {sig['message']}")
    return "\n".join(lines)
