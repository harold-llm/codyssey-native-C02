"""OpenAI 제공자 — Responses API + web_search 도구 (기존 Compass 구현을 수정·분리).

기존 코드는 Chat Completions에 `web_search_preview` 도구를 넘겨 항상 오류 → 폴백되던 문제가
있었다. 웹 검색 도구는 Responses API에서 지원되므로 그쪽으로 옮겼다.
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


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, timeout=config.LLM_TIMEOUT_SECONDS, max_retries=2)

    def _create(self, system: str, messages: list[dict], web_search: bool):
        kwargs: dict = {
            "model": self.model,
            "instructions": system,
            "input": [{"role": m["role"], "content": m["content"]} for m in messages],
            "max_output_tokens": 2000,
        }
        if web_search:
            kwargs["tools"] = [{"type": "web_search_preview"}]
        return self.client.responses.create(**kwargs)

    def chat(self, system: str, messages: list[dict], web_search: bool) -> LLMResult:
        warnings: list[str] = []
        try:
            try:
                resp = self._create(system, messages, web_search)
            except BadRequestError as exc:
                if not web_search or not is_tool_error(error_detail(exc)):
                    raise
                warnings.append("이 모델은 웹 검색을 지원하지 않아 지식·카탈로그 기반으로 답했어요.")
                web_search = False
                resp = self._create(system, messages, False)
        except AuthenticationError:
            raise LLMError("OpenAI API 키가 올바르지 않아요 (.env의 OPENAI_API_KEY 확인).",
                           account_issue=True) from None
        except NotFoundError:
            raise LLMError(f"OpenAI 모델 '{self.model}'을(를) 찾을 수 없어요 (.env의 OPENAI_MODEL 확인).",
                           account_issue=True) from None
        except RateLimitError as exc:
            if getattr(exc, "code", None) == "insufficient_quota" or is_billing_error(error_detail(exc)):
                raise LLMError("OpenAI 계정의 크레딧(사용 한도)이 부족해 호출하지 못했어요 (OpenAI Billing에서 충전).",
                               account_issue=True) from None
            raise LLMError("OpenAI API 사용 한도에 도달했어요. 잠시 후 다시 시도해 주세요.") from None
        except BadRequestError as exc:
            raise LLMError(f"OpenAI 요청이 거부되었어요: {error_detail(exc)}"[:180]) from None
        except APIStatusError as exc:
            raise LLMError(f"OpenAI 서버 오류({exc.status_code})입니다. 잠시 후 다시 시도해 주세요.") from None
        except APIConnectionError:
            raise LLMError("OpenAI API에 연결하지 못했습니다 (네트워크 확인).") from None

        text = (getattr(resp, "output_text", "") or "").strip()
        if not text:
            raise LLMError("AI 응답이 비어 있습니다.")

        sources: list[dict] = []
        seen: set[str] = set()
        searched = False
        for item in getattr(resp, "output", None) or []:
            itype = getattr(item, "type", "")
            if itype == "web_search_call":
                searched = True
            if itype != "message":
                continue
            for part in getattr(item, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    if getattr(ann, "type", "") != "url_citation":
                        continue
                    url = getattr(ann, "url", None)
                    if url and url not in seen:
                        seen.add(url)
                        sources.append({"url": url, "title": getattr(ann, "title", None) or url})
        return LLMResult(text=text, sources=sources, web_search_used=searched, warnings=warnings)
