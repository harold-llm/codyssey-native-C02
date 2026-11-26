#!/bin/sh
# Compass 로컬 실행 스크립트 (macOS / Linux)
#   ./run.sh          가상환경 준비(최초 1회) 후 서버 실행 → http://127.0.0.1:8000
#   ./run.sh setup    가상환경 생성 + 패키지 설치만
#   ./run.sh test     스모크 테스트 (API 키·네트워크 불필요)
#   ./run.sh seed [--persona adult|teen|child|preschool] [--reset]   샘플 데이터 저장
set -e
cd "$(dirname "$0")"

VENV=.venv
PY="$VENV/bin/python"

setup() {
  if [ ! -x "$PY" ]; then
    echo "▶ 가상환경 생성 ($VENV)"
    python3 -m venv "$VENV"
  fi
  if [ ! -f "$VENV/.installed" ] || [ requirements.txt -nt "$VENV/.installed" ]; then
    echo "▶ 패키지 설치"
    "$PY" -m pip install --upgrade pip -q
    "$PY" -m pip install -r requirements.txt -q
    touch "$VENV/.installed"
  fi
  if [ ! -f .env ]; then
    cp .env.example .env
    echo "▶ .env를 만들었습니다. AI 모드를 쓰려면 ANTHROPIC_API_KEY(또는 OPENAI_API_KEY)를 입력하세요."
    echo "  (키가 없어도 카탈로그 규칙 기반 '오프라인 추천' 모드로 동작합니다)"
  fi
}

case "$1" in
  setup) setup ;;
  test)  setup; exec "$PY" scripts/smoke_test.py ;;
  seed)  setup; shift; exec "$PY" scripts/seed_records.py "$@" ;;
  *)     setup; exec "$PY" backend/main.py ;;
esac
