"""샘플 프로필 + 학습 기록(100개+) 생성 — 로컬 시연·테스트용.

카탈로그 콘텐츠와 연결된 기록(content_id)을 만들어, 추천 재정렬·레벨 신호가 실제로 보이게 한다.

사용법 (저장소 루트에서):
  python scripts/seed_records.py --dry-run              # 출력만 (저장 안 함)
  python scripts/seed_records.py --persona adult        # 현재 저장소(기본: .data/compass.json)에 저장
  python scripts/seed_records.py --persona child --reset  # 기존 로컬 데이터를 지우고 저장
페르소나: adult(성인 L4 소설 읽기) · teen(고2 L5 수능) · child(초3 L3) · preschool(4세 L2)
"""
import argparse
import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from services import catalog, retriever, store  # noqa: E402

PERSONAS = {
    "adult": {"age_band": "18+", "level": "L4", "confidence": "high", "goals": "영어 소설 읽기",
              "interests": "미드, 여행", "focus_skill": "reading", "daily_minutes": 30},
    "teen": {"age_band": "13-17", "level": "L5", "confidence": "low", "goals": "수능 영어 대비",
             "interests": "과학, 음악", "focus_skill": "reading", "daily_minutes": 40},
    "child": {"age_band": "7-12", "level": "L3", "confidence": "high", "goals": "집에서 꾸준히 영어책 읽기",
              "interests": "공룡, 우주", "focus_skill": "reading", "daily_minutes": 20},
    "preschool": {"age_band": "3-6", "level": "L2", "confidence": "low", "goals": "영어 소리와 친해지기",
                  "interests": "동물, 노래", "focus_skill": "listening", "daily_minutes": 15},
}


def generate(profile: dict, days: int) -> list[dict]:
    rng = random.Random(42)  # 시드 고정 → 재실행해도 동일한 데이터
    hits = retriever.search(retriever.query_from_profile(profile, top_k=8))
    pool = [h["item"] for h in hits] or list(catalog.items())[:8]
    today = dt.date.today()
    records = []
    for i in range(days, -1, -1):
        day = today - dt.timedelta(days=i)
        if rng.random() < 0.22:  # 쉬는 날
            continue
        for _ in range(rng.randint(1, 2)):
            it = rng.choice(pool)
            skill = profile.get("focus_skill") if profile.get("focus_skill") in it["skills"] else it["skills"][0]
            records.append({
                "date": day.isoformat(),
                "value": max(5, min(90, int(rng.gauss(it["minutes"], 6)))),
                "memo": it["title"],
                "skill": skill,
                "reaction": rng.choices(["easy", "just_right", "hard"], weights=[25, 60, 15])[0],
                "content_id": it["id"],
            })
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", choices=sorted(PERSONAS), default="adult")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true", help="저장 전에 로컬 데이터(file/memory)를 비움")
    args = ap.parse_args()

    profile = PERSONAS[args.persona]
    records = generate(profile, args.days)
    if args.dry_run:
        print(json.dumps({"profile": profile, "records": records[:5]}, ensure_ascii=False, indent=2))
        print(f"… 총 {len(records)}개 생성 (저장 안 함)")
        return

    if store.backend() == "memory":
        print("STORE_BACKEND=memory 에서는 저장해도 프로세스 종료와 함께 사라집니다.")
        print("로컬에서는 기본값(file)을 쓰거나 --dry-run으로 확인하세요.")
        sys.exit(1)
    if args.reset:
        if store.firebase_enabled():
            print("--reset은 Firestore에서 지원하지 않습니다 (데이터 보호).")
            sys.exit(1)
        store.reset_all()

    store.set_profile(profile)
    for r in records:
        store.add_record(r)
    print(f"[{store.backend()}] 프로필({args.persona}) + 기록 {len(records)}개를 저장했습니다.")


if __name__ == "__main__":
    main()
