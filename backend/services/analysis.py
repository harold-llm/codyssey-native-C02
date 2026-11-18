"""학습 기록 요약 계산 — 프롬프트 주입(컨텍스트 주입)과 UI 요약 화면에 사용."""
from datetime import date, timedelta
from typing import Optional


def _d(v: str) -> date:
    return date.fromisoformat(v)


def build_summary(records: list[dict], profile: Optional[dict] = None) -> dict:
    profile = profile or {}
    if not records:
        return {
            "period": None,
            "count": 0,
            "metrics": {"total": 0, "average": 0, "max": 0, "min": 0},
            "trend": "기록 없음",
            "streak": 0,
            "skill_distribution": {},
            "reaction": {"easy": 0, "just_right": 0, "hard": 0},
            "recent_days": [],
            "level": profile.get("level"),
        }

    values = [r["value"] for r in records]
    dates = [_d(r["date"]) for r in records]
    latest, oldest = max(dates), min(dates)

    # 최근 2주 vs 직전 2주 (일평균 대비)
    r_start = latest - timedelta(days=13)
    p_start = latest - timedelta(days=27)
    recent = [r["value"] for r in records if _d(r["date"]) >= r_start]
    prev = [r["value"] for r in records if p_start <= _d(r["date"]) < r_start]
    if not prev:
        trend = "기록 초기"
    else:
        r_avg, p_avg = sum(recent) / 14, sum(prev) / 14
        if p_avg == 0:
            trend = "상승 (직전 2주 기록 없음)"
        else:
            pct = (r_avg - p_avg) / p_avg * 100
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

    # 연속 기록일 (최근 기록일 기준)
    active = set(dates)
    streak, d = 0, latest
    while d in active:
        streak += 1
        d -= timedelta(days=1)

    # 최근 14일 일별 학습량 (그래프용)
    recent_days = []
    for i in range(13, -1, -1):
        day = latest - timedelta(days=i)
        total = sum(r["value"] for r in records if r["date"] == day.isoformat())
        recent_days.append({"date": day.isoformat(), "minutes": total})

    return {
        "period": f"{oldest.isoformat()} ~ {latest.isoformat()}",
        "count": len(records),
        "metrics": {
            "total": sum(values),
            "average": round(sum(values) / len(values)),
            "max": max(values),
            "min": min(values),
        },
        "trend": trend,
        "streak": streak,
        "skill_distribution": skill_dist,
        "reaction": reaction,
        "recent_days": recent_days,
        "level": profile.get("level"),
    }


def summary_text(summary: dict) -> str:
    """요약을 시스템 프롬프트에 넣을 텍스트로 변환."""
    if not summary["count"]:
        return "아직 학습 기록이 없습니다."
    m = summary["metrics"]
    lines = [
        f"- 기간: {summary['period']} ({summary['count']}개 기록, {summary['streak']}일 연속)",
        f"- 총 학습량: {m['total']}분 (일평균 {m['average']}분, 최대 {m['max']}분, 최소 {m['min']}분)",
        f"- 최근 추세: {summary['trend']}",
    ]
    if summary["skill_distribution"]:
        parts = [
            f"{k} {v}분"
            for k, v in sorted(summary["skill_distribution"].items(), key=lambda x: -x[1])
        ]
        lines.append(f"- 스킬 분포: {' / '.join(parts)}")
    r = summary["reaction"]
    lines.append(f"- 반응: 쉬움 {r['easy']} / 적정 {r['just_right']} / 어려움 {r['hard']}")
    return "\n".join(lines)
