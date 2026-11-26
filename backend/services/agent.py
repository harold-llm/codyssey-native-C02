"""Compass 추천 에이전트 — 한 번의 채팅 턴을 처리하는 오케스트레이터.

    사용자 메시지
      → ① 가드레일 의도 분류 (범위 밖이면 LLM 없이 전문가 안내로 종료)
      → ② 학습 요약 계산 (기록·프로필 → 추세·반응·레벨 신호)
      → ③ 로컬 RAG 검색 (카탈로그 TF-IDF + 레벨·스킬·시간·반응 이력)
      → ④ LLM 응답 (Claude/OpenAI + 웹 검색, 후보를 근거로 주입)
           └ 키 없음·호출 실패 → 규칙 기반 로컬 응답으로 폴백
      → ⑤ 후처리 (표현 완화 + AI 작성 표시)
"""
from dataclasses import asdict, dataclass, field

import config
from services import guardrails, llm, local_coach, retriever
from services.analysis import build_summary
from services.llm import LLMError, get_provider
from services.prompts import PROMPT_VERSION, build_system_prompt

HISTORY_LIMIT = 12
SHOW_CARDS_FOR = ("recommend", "method", "progress")


@dataclass
class AgentReply:
    reply: str
    intent: str
    mode: str  # claude | openai | local | guardrail
    sources: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    web_search_used: bool = False
    prompt_version: str = PROMPT_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_history(history: list[dict]) -> list[dict]:
    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-HISTORY_LIMIT:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    # 첫 메시지는 user여야 한다 (환영 문구 등 앞쪽 assistant 메시지 제거)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _local_reply(intent: str, message: str, profile: dict, summary: dict, hits: list[dict]) -> str:
    if intent == "placement":
        return local_coach.placement(profile, summary)
    if intent == "progress":
        return local_coach.progress(profile, summary, hits)
    if intent == "method":
        return local_coach.method(profile, retriever.detect_skill(message), hits)
    if intent == "recommend":
        return local_coach.recommend(profile, hits, summary)
    return local_coach.general(profile)


def respond(message: str, history: list[dict], profile: dict, records: list[dict]) -> AgentReply:
    intent = guardrails.classify(message)
    if intent == "out_of_scope":
        return AgentReply(reply=guardrails.out_of_scope_reply(), intent=intent, mode="guardrail")

    summary = build_summary(records, profile)
    q = retriever.query_from_profile(
        profile, text=message, free_only=(retriever.wants_free(message) or None), top_k=5
    )
    hits = retriever.search(q, summary)
    cards = retriever.to_cards(hits[:3]) if intent in SHOW_CARDS_FOR else []

    warnings: list[str] = []
    provider = get_provider()
    reason = llm.paused_reason() if provider is not None else None
    if reason:
        # 직전에 계정 오류(크레딧·키)가 났음 → API를 다시 부르지 않고 바로 로컬 응답
        warnings.append(f"{reason} 그래서 카탈로그 규칙 기반으로 답했어요.")
        provider = None
    if provider is not None:
        system = build_system_prompt(profile, summary, retriever.candidates_text(hits), intent)
        convo = _clean_history(history) + [{"role": "user", "content": message}]
        try:
            result = provider.chat(system, convo, web_search=config.ENABLE_WEB_SEARCH)
            return AgentReply(
                reply=guardrails.finalize(result.text),
                intent=intent,
                mode=provider.name,
                sources=result.sources,
                recommendations=cards,
                warnings=result.warnings,
                web_search_used=result.web_search_used,
            )
        except LLMError as exc:
            print(f"[compass] LLM 실패 → 로컬 응답: {exc}")
            if exc.account_issue:
                llm.pause(str(exc))
            warnings.append(f"{exc} 그래서 카탈로그 규칙 기반으로 답했어요.")

    reply = _local_reply(intent, message, profile, summary, hits[:3])
    return AgentReply(
        reply=guardrails.finalize(reply),
        intent=intent,
        mode="local",
        recommendations=cards,
        warnings=warnings,
    )
