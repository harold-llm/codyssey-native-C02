"""LLM 제공자 선택 (Bloomy-AI `llm.client_from_env` 방식 계승).

LLM_PROVIDER=auto  → OPENROUTER_API_KEY → OpenRouter, 없으면 ANTHROPIC_API_KEY → Claude,
                     없으면 OPENAI_API_KEY → OpenAI, 모두 없으면 None(규칙 기반 로컬 모드)
LLM_PROVIDER=openrouter | anthropic | openai | local 로 명시할 수도 있다.

SDK는 실제로 쓸 때만 import 한다 — 패키지나 키가 없어도 서비스는 로컬 모드로 동작.
"""
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

import config


class LLMError(RuntimeError):
    """제공자 호출 실패 (키·네트워크·한도·거절 등). 메시지는 사용자에게 보여도 안전해야 한다.

    account_issue=True: 크레딧 부족·키 오류처럼 사용자가 계정 설정을 고치기 전까지 계속 실패할
    오류. 에이전트는 이때 잠시 LLM 호출을 멈추고 로컬 응답으로 바로 답한다.
    """

    def __init__(self, message: str, *, account_issue: bool = False):
        super().__init__(message)
        self.account_issue = account_issue


def error_detail(exc: BaseException) -> str:
    """SDK 예외에서 사람이 읽을 오류 메시지만 꺼낸다 (요청 본문 등은 제외)."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return str(getattr(exc, "message", "") or exc)


def is_billing_error(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("credit balance", "billing", "insufficient_quota", "exceeded your current quota"))


def is_tool_error(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("web_search", "web search", "tool"))


@dataclass
class LLMResult:
    text: str
    sources: list[dict] = field(default_factory=list)
    web_search_used: bool = False
    warnings: list[str] = field(default_factory=list)


class Provider(Protocol):
    name: str
    model: str

    def chat(self, system: str, messages: list[dict], web_search: bool) -> LLMResult: ...


_provider: Optional[Provider] = None
_resolved = False
_init_error: Optional[str] = None


def _build() -> Optional[Provider]:
    choice = config.LLM_PROVIDER
    if choice in ("local", "none", "off"):
        return None
    if choice == "openrouter" or (choice == "auto" and config.OPENROUTER_API_KEY):
        if not config.OPENROUTER_API_KEY:
            raise LLMError("LLM_PROVIDER=openrouter 이지만 OPENROUTER_API_KEY가 없습니다")
        from services.llm.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL, config.OPENROUTER_BASE_URL)
    if choice in ("anthropic", "claude") or (choice == "auto" and config.ANTHROPIC_API_KEY):
        if not config.ANTHROPIC_API_KEY:
            raise LLMError("LLM_PROVIDER=anthropic 이지만 ANTHROPIC_API_KEY가 없습니다")
        from services.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL, config.CLAUDE_EFFORT)
    if choice == "openai" or (choice == "auto" and config.OPENAI_API_KEY):
        if not config.OPENAI_API_KEY:
            raise LLMError("LLM_PROVIDER=openai 이지만 OPENAI_API_KEY가 없습니다")
        from services.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(config.OPENAI_API_KEY, config.OPENAI_MODEL)
    return None


def get_provider() -> Optional[Provider]:
    """설정된 제공자 (없으면 None → 로컬 모드). 초기화 실패도 로컬 모드로 폴백."""
    global _provider, _resolved, _init_error
    if not _resolved:
        try:
            _provider = _build()
        except (LLMError, ImportError) as exc:
            _init_error = str(exc)
            print(f"[compass] LLM 초기화 실패 → 로컬 모드: {_init_error}")
            _provider = None
        _resolved = True
    return _provider


# ── 계정 오류 시 일시 중단 ─────────────────────────────────────
# 크레딧 부족·키 오류는 사용자가 고치기 전까지 매번 실패하므로, 메시지마다 API를 다시
# 부르지 않고 잠시 로컬 응답으로 바로 답한다. 서버를 재시작하면 즉시 다시 시도한다.
PAUSE_SECONDS = 600
_paused_until = 0.0
_pause_reason: Optional[str] = None


def pause(reason: str, seconds: float = PAUSE_SECONDS) -> None:
    global _paused_until, _pause_reason
    _paused_until = time.monotonic() + seconds
    _pause_reason = reason


def paused_reason() -> Optional[str]:
    """일시 중단 중이면 그 이유, 아니면 None."""
    global _pause_reason
    if _pause_reason and time.monotonic() >= _paused_until:
        _pause_reason = None
    return _pause_reason


def status() -> dict:
    p = get_provider()
    return {
        "provider": p.name if p else "local",
        "model": p.model if p else None,
        "web_search": bool(p) and config.ENABLE_WEB_SEARCH,
        "init_error": _init_error,
        "paused_reason": paused_reason() if p else None,
    }
