"""AI 추천 에이전트 — OpenAI Chat Completions + web_search 도구.

- 미리 준비한 카탈로그로 제한하지 않고 AI 지식 + 실시간 웹 검색(커뮤니티·유튜브 등)으로 추천
- 모든 추천에 적합 이유 설명 + 출처 인용(UI "참고 출처" 표시)
- 모든 응답에 "자기 주도 집중 시간" 리마인드 포함 (시스템 프롬프트에 내장)
"""
from typing import Optional

from fastapi import HTTPException
from openai import OpenAI, OpenAIError

from config import ENABLE_WEB_SEARCH, OPENAI_API_KEY, OPENAI_MODEL
from services.analysis import summary_text

_client: Optional[OpenAI] = None

PROMPT_VERSION = "v1.0"


def _openai() -> OpenAI:
    global _client
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY가 설정되지 않았습니다. .env 또는 배포 환경 변수에 API 키를 설정해 주세요.",
        )
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def build_system_prompt(profile: dict, summary: dict) -> str:
    age = profile.get("age_band") or "미설정"
    level = profile.get("level") or "미판정"
    conf = {"high": "높음", "low": "낮음"}.get(profile.get("confidence") or "", "미확인")
    goals = profile.get("goals") or "미설정"
    minutes = profile.get("daily_minutes") or "미설정"

    return f"""당신은 "Compass"의 영어 학습 컨시어지 AI입니다. 학습자의 수준과 목표에 맞는 영어 학습 콘텐츠를 찾아주고, 스스로 꾸준히 학습하게 돕는 것이 역할입니다.

[프로필]
- 연령대: {age}
- 현재 레벨: {level} (신뢰도: {conf})
- 목표: {goals}
- 하루 학습 시간: {minutes}분

[학습 요약]
{summary_text(summary)}

[응답 지침 — 모든 대화에서 지키세요]
1. 콘텐츠 추천 시:
   - 학습자의 레벨·연령대·목표에 맞는 구체적 콘텐츠(유튜브 채널·영상, 교재, 앱, 웹사이트, 커뮤니티, 팟캐스트 등)를 2~3개 추천합니다.
   - 최신 콘텐츠와 실제 존재 여부를 확인하려면 웹 검색을 적극 활용하세요.
   - 각 추천마다 "이 학습자에게 왜 적합한지" 이유를 1~2문장으로 반드시 설명하세요. (레벨 적합성, 목표와의 연결, 콘텐츠 특징)
   - 웹 검색에서 확인한 출처가 있으면 링크를 함께 제시하세요.
2. 자기 주도 집중 시간 강조 (매 응답 필수, 1문장):
   - "스스로 집중해서 들인 시간이 영어를 자라게 한다"는 원칙을 한 문장으로 자연스럽게 리마인드합니다.
3. 기록·자기 점검 안내 (첫 대화, 목표 설정, 진도 질문 시 특히):
   - 학습 직후 「학습 기록」 탭에 시간·내용·느낌(쉬움/적정/어려움)을 기록하도록 안내합니다.
   - 주기적으로 「요약」을 확인하고, 채팅으로 "요즘 내 학습은 어때?"라고 묻도록 권합니다.
   - '쉬움' 또는 '어려움' 반응이 반복되면 레벨 재점검을 제안합니다.
4. 레벨이 미판정 또는 신뢰도가 낮으면: 먼저 짧은 질문(연령대, 영어 노출 정도, 목표)으로 파악한 뒤 L1~L6 중 레벨을 제안하고 이유를 설명합니다.
   - L1 초입문(소리) / L2 기본 듣기 / L3 짧은 문장 / L4 기초 읽기 / L5 쉬운 텍스트 독해 / L6 실제 자료
5. 금지 사항: 진단·평가·보장 표현("당신의 레벨은 낮다", "O주면 마스터" 등). 유료 콘텐츠는 가격과 무료 대안을 명시합니다.
6. 답변은 한국어로, 한 스크린 분량(약 200~350자)으로 간결하게. 목록은 줄바꿈으로 정리합니다.
7. 모든 답변 맨 끝에 "(AI가 작성했습니다)"를 붙입니다.

(프롬프트 {PROMPT_VERSION})"""


def chat(
    message: str, history: list[dict], profile: dict, summary: dict
) -> tuple[str, list[dict]]:
    """AI 응답 + 출처(citations) 반환."""
    system = build_system_prompt(profile, summary)
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history[-12:]:
        role, content = m.get("role"), m.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    use_web = ENABLE_WEB_SEARCH
    try:
        resp = _complete(messages, use_web)
    except OpenAIError:
        if use_web:
            # 웹 검색 도구 미지원 모델 등 → 일반 응답으로 폴백
            try:
                resp = _complete(messages, False)
            except OpenAIError:
                raise HTTPException(
                    502, "AI 서비스에 연결하지 못했습니다. API 키·모델 설정을 확인해 주세요."
                )
        else:
            raise HTTPException(502, "AI 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    reply = (resp.choices[0].message.content or "").strip()
    if not reply:
        raise HTTPException(502, "AI 응답이 비어 있습니다. 다시 시도해 주세요.")
    return reply, _sources(resp)


def _complete(messages: list[dict], use_web: bool):
    kwargs: dict = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.4,
    }
    if use_web:
        kwargs["tools"] = [{"type": "web_search_preview"}]
    return _openai().chat.completions.create(**kwargs)


def _sources(resp) -> list[dict]:
    """웹 검색 인용(url_citation) 추출 — UI의 '참고 출처'로 표시."""
    out: list[dict] = []
    seen: set[str] = set()
    anns = getattr(resp.choices[0].message, "annotations", None) or []
    for a in anns:
        if getattr(a, "type", "") != "url_citation":
            continue
        u = getattr(a.url_citation, "url", None)
        if not u or u in seen:
            continue
        seen.add(u)
        out.append({"url": u, "title": getattr(a.url_citation, "title", None) or u})
    return out
