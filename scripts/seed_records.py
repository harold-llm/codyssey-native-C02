"""샘플 학습 기록(100개+) 생성 — 개발·테스트용.

사용법:
  python scripts/seed_records.py --dry-run   # 콘솔에 출력만 (저장 안 함)
  python scripts/seed_records.py             # Firestore에 저장 (FIREBASE_SERVICE_ACCOUNT_JSON 필요)
"""
import argparse
import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from services import store  # noqa: E402

SKILLS = ["listening", "reading", "speaking", "vocabulary", "overall"]
MEMOS = {
    "listening": ["유튜브 영자 영상 1개", "영어 팟캐스트 듣기", "노래로 단어 익히기"],
    "reading": ["그레디드 리더 1챕터", "영어 그림책 읽기", "짧은 뉴스 기사 읽기"],
    "speaking": ["쉐도잉 연습", "영어로 혼자 말하기 연습"],
    "vocabulary": ["단어장 20개", "어플로 단어 암기"],
    "overall": ["종합 학습 앱 1일분"],
}


def generate(days: int) -> list[dict]:
    rng = random.Random(42)  # 시드 고정 → 재실행해도 동일한 데이터
    today = dt.date.today()
    records = []
    for i in range(days, -1, -1):
        day = today - dt.timedelta(days=i)
        if rng.random() < 0.25:  # 휴일
            continue
        for _ in range(rng.randint(1, 2)):
            skill = rng.choice(SKILLS)
            records.append(
                {
                    "date": day.isoformat(),
                    "value": rng.randint(10, 60),
                    "memo": rng.choice(MEMOS[skill]),
                    "skill": skill,
                    "reaction": rng.choices(["easy", "just_right", "hard"], weights=[25, 60, 15])[0],
                }
            )
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records = generate(args.days)
    if args.dry_run:
        print(json.dumps(records[:5], ensure_ascii=False, indent=2))
        print(f"… 총 {len(records)}개 생성")
        return

    if not store.firebase_enabled():
        print("FIREBASE_SERVICE_ACCOUNT_JSON이 없어 Firestore 저장 불가입니다.")
        print("--dry-run으로 데이터만 확인하거나, 환경 변수를 설정한 뒤 다시 실행하세요.")
        sys.exit(1)

    for r in records:
        store.add_record(r)
    print(f"{len(records)}개 기록을 Firestore에 저장했습니다")


if __name__ == "__main__":
    main()
