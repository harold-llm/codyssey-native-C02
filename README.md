# 🧭 Compass — 전 연령 영어 학습 콘텐츠 추천 AI

학습자의 영어 수준(레벨)과 학습 이력을 파악해 **"지금 나에게 맞는 콘텐츠"**를 찾아주고, **왜 좋은지 이유**까지 설명해 주는 AI 에이전트 웹 서비스입니다. (3~6세 부모 대용 ~ 성인까지)

## 핵심 특징

- **카탈로그 제한 없음**: AI의 기존 지식 + **실시간 웹 검색**(커뮤니티·유튜브 등)으로 최신·실존 콘텐츠를 찾아 추천
- **추천마다 이유 설명**: "이 학습자에게 왜 적합한지"(레벨 적합성·목표 연결·특징) + 출처 링크("참고 출처" 표시)
- **자기 주도 집중 시간 강조 (핵심 가치)**: "스스로 집중해서 들인 시간이 영어를 자라게 한다" — 채팅 상단 상시 배너, 요약 화면 핵심 원칙 섹션, **모든 AI 응답 1문장 리마인드**
- **자기 기록·점검 안내**: 학습 후 기록(시간·내용·느낌) → 요약에서 추세·스킬 분포 확인 → AI에게 "요즘 내 학습은 어때?" 질문하는 루프를 안내
- **레벨 체계 L1~L6**: 채팅 플레이스먼트로 판정, 학습 기록의 반응(쉬움/적정/어려움)으로 재조정

## 화면 (바닐라 HTML/CSS/JS, 모바일 퍼스트)

| 탭 | 내용 |
|---|---|
| 💬 채팅 | AI 추천·조언, 로딩 표시, 출처 표시, "레벨 다시 보기" |
| 📝 기록 | 학습 기록 CRUD (날짜/시간/내용/스킬/느낌) |
| 🗂 대화 | 대화 목록, 불러오기, 삭제 (채팅 시 자동 저장) |
| 📊 요약 | **핵심 원칙** + **기록·점검 안내** + 프로필 저장 + 통계 + 14일 차트 |

## 기술 스택

- **백엔드**: Python 3.10+, FastAPI, Pydantic, firebase-admin, openai
- **DB**: Firebase Firestore (`data`·`conversations`·`profile`) — 미설정 시 인메모리(개발용)
- **AI**: OpenAI Chat Completions + `web_search_preview` 도구 (출처 인용 추출)
- **프론트엔드**: HTML/CSS/JS (프레임워크 없음), 다크 모드
- **배포**: Vercel (FastAPI 서버리스가 프론트엔드 정적 파일도 함께 서빙 → 1개 URL)

## 로컬 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # OPENAI_API_KEY (최소) 입력
cd backend && uvicorn main:app --reload
```

- 서비스: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- 샘플 데이터: `python scripts/seed_records.py --dry-run` (Firestore 저장: 환경 변수 설정 후 `--dry-run` 없이 실행)
- API 검증: `python scripts/smoke_test.py` (서버 기동·API 키 없이 전 엔드포인트 스모크 테스트)

## 환경 변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API 키 |
| `OPENAI_MODEL` | - | 기본 `gpt-4o-mini` (웹 검색 도구 지원 모델 권장) |
| `ENABLE_WEB_SEARCH` | - | 웹 검색 on/off, 기본 `true` (미지원 모델이면 자동 폴백) |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | - | 서비스 계정 키 JSON(한 줄). 미설정 시 인메모리 저장(재시작 시 소실) |
| `ALLOWED_ORIGINS` | - | CORS 허용 오리진, 기본 `*` (동일 원신 배포라 보통 그대로) |

## Vercel 배포

1. 리포지토리를 GitHub에 푸시
2. Vercel에서 프로젝트를 import (또는 `npx vercel`)
   - `vercel.json`이 있으면 자동으로 FastAPI 서버리스(`@vercel/python`)로 빌드
3. 환경 변수 설정 (`OPENAI_API_KEY` 필수, 그 외 위 표 참고)
4. 배포 URL 접속 → 서비스 + `/docs`(Swagger) 동일 URL에서 확인

> 참고: `FIREBASE_SERVICE_ACCOUNT_JSON`은 JSON **전체를 한 줄**로 입력하세요.

## API

| Method | Path | 설명 |
|---|---|---|
| POST | /api/data | 학습 기록 추가 |
| GET | /api/data | 학습 기록 목록 |
| PUT | /api/data/{id} | 학습 기록 수정 |
| DELETE | /api/data/{id} | 학습 기록 삭제 |
| GET | /api/data/summary | 학습 요약 (프롬프트 주입용) |
| POST | /api/conversations | 대화 저장 |
| GET | /api/conversations | 대화 목록 |
| GET | /api/conversations/{id} | 대화 전체(messages) 조회 |
| DELETE | /api/conversations/{id} | 대화 삭제 |
| POST | /api/chat | AI 채팅 (요약·프로필 주입 + 웹 검색 + 자동 저장) |
| GET / PUT | /api/profile | 프로필 조회 / 수정 (레벨·연령대·목표) |
| GET | /api/health | 헬스체크 |

## 프로젝트 구조

```
├── backend/
│   ├── main.py            # 앱 초기화, CORS, 정적 파일 서빙
│   ├── config.py          # 환경 변수
│   ├── routers/           # data · conversations · chat · profile
│   ├── services/          # store(Firestore/메모리) · analysis(요약) · ai(프롬프트·GPT·웹검색)
│   └── models/schemas.py  # Pydantic 검증
├── frontend/              # index.html · style.css · app.js
├── scripts/
│   ├── seed_records.py    # 학습 기록 샘플 생성
│   └── smoke_test.py      # 인프로세스 API 스모크 테스트
├── vercel.json
└── requirements.txt
```

## 개발 노트

- **인메모리 모드**: `FIREBASE_SERVICE_ACCOUNT_JSON` 미설정 시 데이터는 메모리에만 존재합니다 (서버 재시작 시 소실). 로컬 UI/AI 흐름 테스트에는 충분합니다.
- **웹 검색**: `web_search_preview`는 일부 모델에서만 지원됩니다. 지원되지 않는 모델이면 자동으로 일반 응답(지식 기반)으로 폴백되며, 원하면 `ENABLE_WEB_SEARCH=false`로 명시 비활성화.
- **Serverless + Firestore**: Firestore Python SDK는 gRPC 기반이라 서버리스 콜드스타트에서 첫 요청이 느릴 수 있습니다. 문제가 발생하면 DB 교체(예: SQLite/Supabase)를 검토하세요.
- **비용**: `max_tokens=1000` 제한 + 최근 12개 메시지만 컨텍스트에 포함. 개발 시 `ENABLE_WEB_SEARCH`를 꺼놓고 소규모 데이터로 먼저 검증하세요.
