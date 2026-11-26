"""OpenRouter 제공자 — 키 하나로 Claude·GPT 등 여러 모델 사용 (OpenAI 호환 Chat Completions).

- 모델 ID는 OpenRouter 표기: anthropic/claude-opus-5.5, anthropic/claude-haiku-5.5, openai/gpt-4o-mini …
- 웹 검색: OpenRouter `web` 플러그인 (모델 무관). 인용은 message.annotations의 url_citation
- 크레딧 부족은 HTTP 402로 온다 → 계정 오류로 처리
"""
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

import config
from services.llm import LLMError, LLMResult, error_detail, is_billing_error, is_tool_error


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, model: str, base_url: str):
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=2,
            # OpenRouter 대시보드에 앱 이름으로 표시되는 선택 헤더
            default_headers={"X-Title": "Compass"},
        )

    def _create(self, system: str, messages: list[dict], web_search: bool):
        extra: dict = {}
        if web_search:
            extra["plugins"] = [{"id": "web", "max_results": 3}]
        if self.model.startswith("anthropic/"):
            extra["reasoning"] = {"effort": config.CLAUDE_EFFORT}
        return self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=4000,
            extra_body=extra or None,
        )

    def chat(self, system: str, messages: list[dict], web_search: bool) -> LLMResult:
        warnings: list[str] = []
        try:
            try:
                resp = self._create(system, messages, web_search)
            except BadRequestError as exc:
                detail = error_detail(exc)
                search_issue = is_tool_error(detail) or "plugin" in detail.lower()
                if not (web_search and search_issue):
                    raise
                warnings.append("웹 검색을 사용할 수 없어 지식·카탈로그 기반으로 답했어요.")
                web_search = False
                resp = self._create(system, messages, False)
        except AuthenticationError:
            raise LLMError("OpenRouter API 키가 올바르지 않아요 (.env의 OPENROUTER_API_KEY 확인).",
                           account_issue=True) from None
        except NotFoundError:
            raise LLMError(f"OpenRouter에서 모델 '{self.model}'을(를) 찾을 수 없어요 (.env의 OPENROUTER_MODEL 확인).",
                           account_issue=True) from None
        except RateLimitError:
            raise LLMError("OpenRouter 사용 한도에 도달했어요. 잠시 후 다시 시도해 주세요.") from None
        except BadRequestError as exc:
            raise LLMError(f"OpenRouter 요청이 거부되었어요: {error_detail(exc)}"[:180]) from None
        except APIStatusError as exc:
            if exc.status_code == 402 or is_billing_error(error_detail(exc)):
                raise LLMError("OpenRouter 크레딧이 부족해 호출하지 못했어요 (openrouter.ai → Credits에서 충전).",
                               account_issue=True) from None
            if exc.status_code == 403:
                raise LLMError(f"OpenRouter가 요청을 막았어요: {error_detail(exc)}"[:180]) from None
            raise LLMError(f"OpenRouter 서버 오류({exc.status_code})예요. 잠시 후 다시 시도해 주세요.") from None
        except APIConnectionError:
            raise LLMError("OpenRouter에 연결하지 못했어요 (네트워크 확인).") from None

        return parse_response(resp, web_search, warnings)


def parse_response(resp, web_search: bool, warnings: list[str]) -> LLMResult:
    choices = getattr(resp, "choices", None) or []
    if not choices:
        # OpenRouter는 일부 상류 오류를 200 + error 본문으로 돌려준다
        raise LLMError("OpenRouter 응답이 비어 있어요. 잠시 후 다시 시도해 주세요.")
    msg = choices[0].message
    text = (getattr(msg, "content", None) or "").strip()
    if not text:
        raise LLMError("AI 응답이 비어 있어요.")
    if getattr(choices[0], "finish_reason", None) == "length":
        warnings.append("응답이 길어 중간에 잘렸을 수 있어요.")

    sources: list[dict] = []
    seen: set[str] = set()
    for ann in getattr(msg, "annotations", None) or []:
        ann = ann if isinstance(ann, dict) else (ann.model_dump() if hasattr(ann, "model_dump") else vars(ann))
        if ann.get("type") != "url_citation":
            continue
        cite = ann.get("url_citation") or ann  # 중첩/평면 형식 모두 지원
        url = cite.get("url")
        if url and url not in seen:
            seen.add(url)
            sources.append({"url": url, "title": cite.get("title") or url})
    return LLMResult(text=text, sources=sources, web_search_used=web_search, warnings=warnings)
