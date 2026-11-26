"""가드레일 — 의도 분류(키워드, 감사 가능) + 범위 밖 안내 + 응답 후처리.

Bloomy-AI `agent/intent.py`·`guardrails.py` 원칙 계승:
- 발달·의학·심리 판단 요청은 LLM을 부르지 않고 고정된 안전 문구로 전문가 안내
- 규칙 판단(의도·레벨 신호)은 LLM 출력이 덮어쓰지 못한다
- 모든 AI 생성 응답에 AI 작성 표시
"""
import re

AI_LABEL = "(AI가 작성했습니다)"

INTENTS = ("out_of_scope", "placement", "progress", "recommend", "method", "general")

_OUT_OF_SCOPE = (
    "발달 지연", "발달지연", "언어 지연", "언어지연", "언어치료", "언어 치료", "자폐", "adhd",
    "난독증", "난독", "학습장애", "학습 장애", "장애가", "우울", "불안장애", "공황", "치료",
    "병원", "약 먹", "질병", "말이 늦", "말이 느려", "정신과", "심리 검사", "심리검사",
)
_PLACEMENT = (
    "레벨", "수준", "실력", "레벨 테스트", "레벨테스트", "몇 단계", "어느 단계", "진단", "테스트",
    "placement", "level",
)
_PROGRESS = (
    "요즘 내 학습", "요즘 학습", "요즘 어때", "학습 어때", "학습은 어때", "진도", "기록 봐", "기록을 봐", "점검", "돌아봐", "피드백",
    "잘하고 있", "얼마나 했", "이번 주", "이번주", "지난주", "통계",
)
_RECOMMEND = (
    "추천", "뭐 볼", "뭘 볼", "뭐 들", "뭘 들", "뭐 읽", "뭘 읽", "뭐 하면", "뭘 하면", "뭐하면",
    "콘텐츠", "교재", "책 ", "그림책", "원서", "채널", "앱", "팟캐스트", "사이트", "자료", "볼만",
    "들을만", "골라", "알려줘", "오늘 뭐", "오늘 뭘",
)
_METHOD = (
    "어떻게", "방법", "공부법", "학습법", "팁", "요령", "루틴", "순서", "how to",
)


def classify(message: str) -> str:
    """우선순위: 범위 밖 > 레벨 > 진도 점검 > 추천 > 방법 > 일반."""
    text = (message or "").casefold()
    compact = re.sub(r"\s+", " ", text)
    if any(w in compact for w in _OUT_OF_SCOPE):
        return "out_of_scope"
    # "내 수준에 맞는 책 알려줘"처럼 콘텐츠를 찾는 말이 함께 있으면 추천으로 본다
    wants_content = any(w in compact for w in ("추천", "콘텐츠", "자료", "책", "영상", "채널", "교재", "앱"))
    if any(w in compact for w in _PLACEMENT) and not wants_content:
        return "placement"
    if any(w in compact for w in _PROGRESS):
        return "progress"
    if any(w in compact for w in _RECOMMEND):
        return "recommend"
    if any(w in compact for w in _METHOD):
        return "method"
    return "general"


def out_of_scope_reply() -> str:
    return "\n".join([
        "말씀해 주셔서 고마워요. 다만 발달·건강·심리에 관한 판단은 Compass가 도울 수 있는 범위를 벗어나요.",
        "",
        "· 아이의 언어 발달이 걱정된다면 소아청소년과 또는 언어재활사(언어치료사) 상담을 권해요.",
        "· 학습 중 지속되는 어려움(읽기 곤란 등)은 학교 상담 선생님이나 전문 기관과 먼저 이야기해 보세요.",
        "· 마음이 많이 힘들다면 정신건강 위기상담 전화 109(24시간)로 바로 도움을 받을 수 있어요.",
        "",
        "Compass는 진단이나 평가 대신, 지금 부담 없이 즐길 수 있는 영어 콘텐츠를 찾는 일을 도울게요. "
        "\"부담 없이 할 수 있는 쉬운 영어 콘텐츠 추천해줘\"처럼 물어봐 주세요.",
        "",
        AI_LABEL,
    ])


# 보장·평가성 표현은 프롬프트로 금지하지만, 혹시 섞여 나오면 완화한다.
_SOFTEN = (
    (re.compile(r"반드시\s*(늘|향상|마스터)"), r"꾸준히 하면 \1"),
    (re.compile(r"(\d+)\s*(주|개월|달)\s*(만에|안에)\s*마스터"), r"\1\2 꾸준히 해 보며 점검"),
    (re.compile(r"레벨이\s*낮(습니다|아요|다)"), "지금 단계에 맞는 자료부터 시작하면 좋아요"),
)


def finalize(reply: str) -> str:
    """응답 후처리: 표현 완화 + AI 작성 표시 보장."""
    text = (reply or "").strip()
    for pattern, repl in _SOFTEN:
        text = pattern.sub(repl, text)
    text = text.replace(AI_LABEL, "").rstrip()
    return f"{text}\n\n{AI_LABEL}"
