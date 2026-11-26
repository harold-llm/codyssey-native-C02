"""Claude 제공자 — Anthropic 공식 Python SDK + 서버 측 웹 검색 도구.

- 웹 검색: `web_search` 서버 도구. 검색 결과 인용(citations)을 출처로 추출
- 긴 검색 턴이 `pause_turn`으로 멈추면 같은 대화를 다시 보내 이어서 진행
- 안전 분류기 거절(`refusal`)에 대비해 지원 모델은 서버 측 fallback을 켠다
- 웹 검색이 조직 설정 등으로 거부되면 도구 없이 한 번 더 시도
"""
import anthropic

import config
from services.llm import LLMError, LLMResult, error_detail, is_billing_error, is_tool_error

# web_search_20260209(동적 필터링)를 지원하는 모델 계열. 그 외(예: Haiku)는 기본 버전 사용.
_DYNAMIC_SEARCH_PREFIXES = ("claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                            "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-5", "claude-mythos-5")
# 서버 측 refusal fallback(`fallbacks: "default"`)을 지원하는 모델
_FALLBACK_PREFIXES = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MAX_CONTINUATIONS = 3


class AnthropicProvider:
    name = "claude"

    def __init__(self, api_key: str, model: str, effort: str = "low"):
        self.model = model
        self.effort = effort if effort in ("low", "medium", "high", "xhigh", "max") else "low"
        self.client = anthropic.Anthropic(
            api_key=api_key, timeout=config.LLM_TIMEOUT_SECONDS, max_retries=2
        )

    def _search_tool(self) -> dict:
        if self.model.startswith(_DYNAMIC_SEARCH_PREFIXES):
            return {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}
        return {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}

    def _create(self, system: str, messages: list[dict], web_search: bool):
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 16000,
            "system": system,
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        if web_search:
            kwargs["tools"] = [self._search_tool()]
        if self.model.startswith(_FALLBACK_PREFIXES):
            return self.client.beta.messages.create(
                betas=[_FALLBACK_BETA], fallbacks="default", **kwargs
            )
        return self.client.messages.create(**kwargs)

    def _run(self, system: str, messages: list[dict], web_search: bool):
        convo = list(messages)
        response = self._create(system, convo, web_search)
        for _ in range(_MAX_CONTINUATIONS):
            if response.stop_reason != "pause_turn":
                break
            # 서버 도구 루프가 멈춘 경우: 응답을 그대로 붙여 다시 보내면 이어서 진행
            convo = convo + [{"role": "assistant", "content": response.content}]
            response = self._create(system, convo, web_search)
        return response

    def chat(self, system: str, messages: list[dict], web_search: bool) -> LLMResult:
        warnings: list[str] = []
        try:
            try:
                response = self._run(system, messages, web_search)
            except anthropic.BadRequestError as exc:
                # 웹 검색 도구 관련 거부(조직 설정 미허용 등)일 때만 도구 없이 재시도
                if not web_search or not is_tool_error(error_detail(exc)):
                    raise
                warnings.append("웹 검색을 사용할 수 없어 지식·카탈로그 기반으로 답했어요.")
                web_search = False
                response = self._run(system, messages, False)
        except anthropic.AuthenticationError:
            raise LLMError("Claude API 키가 올바르지 않아요 (.env의 ANTHROPIC_API_KEY 확인).",
                           account_issue=True) from None
        except anthropic.PermissionDeniedError:
            raise LLMError("이 API 키로는 해당 Claude 모델을 쓸 수 없어요.", account_issue=True) from None
        except anthropic.NotFoundError:
            raise LLMError(f"Claude 모델 '{self.model}'을(를) 찾을 수 없어요 (.env의 ANTHROPIC_MODEL 확인).",
                           account_issue=True) from None
        except anthropic.RateLimitError:
            raise LLMError("Claude API 사용 한도에 도달했어요. 잠시 후 다시 시도해 주세요.") from None
        except anthropic.BadRequestError as exc:
            detail = error_detail(exc)
            if is_billing_error(detail):
                raise LLMError(
                    "Anthropic 계정의 크레딧이 부족해 Claude를 호출하지 못했어요 "
                    "(Claude Console → Plans & Billing에서 충전).",
                    account_issue=True,
                ) from None
            raise LLMError(f"Claude 요청이 거부되었어요: {detail}"[:180]) from None
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude 서버 오류({exc.status_code})입니다. 잠시 후 다시 시도해 주세요.") from None
        except anthropic.APIConnectionError:
            raise LLMError("Claude API에 연결하지 못했습니다 (네트워크 확인).") from None

        if response.stop_reason == "refusal":
            raise LLMError("AI가 이 요청에 답하지 않았습니다.")

        text_parts: list[str] = []
        sources: list[dict] = []
        seen: set[str] = set()
        searched = False
        for block in response.content:
            if block.type == "server_tool_use":
                searched = True
            if block.type != "text":
                continue
            text_parts.append(block.text)
            for c in getattr(block, "citations", None) or []:
                url = getattr(c, "url", None)
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"url": url, "title": getattr(c, "title", None) or url})
        text = "".join(text_parts).strip()
        if not text:
            raise LLMError("AI 응답이 비어 있습니다.")
        if response.stop_reason == "max_tokens":
            warnings.append("응답이 길어 중간에 잘렸을 수 있어요.")
        return LLMResult(text=text, sources=sources, web_search_used=searched, warnings=warnings)
