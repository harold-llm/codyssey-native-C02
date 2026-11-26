"""인프로세스 스모크 테스트 — 서버 기동·API 키·네트워크 없이 전 엔드포인트와 에이전트 로직을 검증한다.

실행: python scripts/smoke_test.py   (또는 ./run.sh test)
인메모리 저장소 + 로컬(규칙 기반) LLM 모드로 강제해, 실제 데이터 파일과 API 과금에 영향이 없다.
"""
import os
import sys

# 반드시 앱 import 전에 설정 (.env보다 우선)
os.environ["STORE_BACKEND"] = "memory"
os.environ["LLM_PROVIDER"] = "local"
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from services import analysis, catalog, guardrails, retriever  # noqa: E402

client = TestClient(app)
passed = 0


def check(name: str, condition: bool, extra: str = "") -> None:
    global passed
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
    if not condition:
        sys.exit(1)
    passed += 1


def unit_tests() -> None:
    # 카탈로그
    items = catalog.items()
    bands = {b for it in items for b in it["age_bands"]}
    check("catalog: 전 연령대 포함", bands == set(catalog.AGE_BANDS), f"{len(items)}개")
    for band in catalog.AGE_BANDS:
        n = sum(1 for it in items if band in it["age_bands"])
        check(f"catalog: {band} 항목 ≥ 8", n >= 8, f"{n}개")

    # 가드레일 의도 분류
    cases = {
        "우리 아이가 말이 늦은데 자폐일까요?": "out_of_scope",
        "내 레벨 확인해줘": "placement",
        "요즘 내 학습은 어때?": "progress",
        "리딩 자료 추천해줘": "recommend",
        "리스닝은 어떻게 공부해?": "method",
        "안녕": "general",
        "오늘 배운 거 요약을 해줘": "general",
    }
    for msg, want in cases.items():
        got = guardrails.classify(msg)
        check(f"intent '{msg}' → {want}", got == want, got)
    check("finalize: AI 표시 1회", guardrails.finalize("hi (AI가 작성했습니다)").count(guardrails.AI_LABEL) == 1)

    # 검색: 연령·레벨 필터와 스킬 가산
    hits = retriever.search(retriever.Query(text="그림책 읽기", age_band="3-6", level=2, top_k=5))
    check("retriever: 3-6 필터", all("3-6" in h["item"]["age_bands"] for h in hits), str([h["item"]["id"] for h in hits]))
    check("retriever: 레벨 ±1 이내", all(h["item"]["level_min"] <= 3 and h["item"]["level_max"] >= 1 for h in hits))
    hits = retriever.search(retriever.Query(text="뉴스로 리딩", age_band="18+", level=5, skill="reading", top_k=3))
    check("retriever: 성인 리딩 후보에 reading 포함", all("reading" in h["item"]["skills"] for h in hits[:2]),
          str([h["item"]["id"] for h in hits]))
    check("retriever: 이유 설명 포함", all(h["reasons"] for h in hits))
    hits = retriever.search(retriever.Query(text="회화", age_band="18+", level=5, free_only=True, top_k=6))
    check("retriever: free_only면 유료 제외", all(h["item"]["cost"] != "paid" for h in hits))

    # 레벨 신호: 최근 10개 중 쉬움 7개
    today = date.today()
    recs = [{"date": (today - timedelta(days=i)).isoformat(), "value": 20, "memo": "x",
             "reaction": "easy" if i < 8 else "just_right"} for i in range(10)]
    sig = analysis.level_signal(recs, "L3")
    check("level_signal: 쉬움 반복 → up, L4 제안", bool(sig) and sig["direction"] == "up" and sig["suggested_level"] == "L4")
    s = analysis.build_summary(recs, {"daily_minutes": 30})
    check("summary: 연속 기록·목표", s["streak"] == 10 and s["goal"]["weekly_target"] == 210, f"streak={s['streak']}")


def api_tests() -> None:
    r = client.get("/api/health")
    body = r.json()
    check("GET /api/health", r.status_code == 200 and body["llm"]["provider"] == "local" and body["store"] == "memory", str(body))

    r = client.get("/api/data/summary")
    check("GET /api/data/summary (empty)", r.status_code == 200 and r.json()["count"] == 0)

    today = date.today().isoformat()
    r = client.post("/api/data", json={
        "date": today, "value": 20, "memo": "Super Simple Songs 2곡",
        "skill": "listening", "reaction": "just_right", "content_id": "super-simple-songs",
    })
    check("POST /api/data", r.status_code == 201 and r.json().get("id"), str(r.json())[:120])
    rid = r.json()["id"]

    r = client.post("/api/data", json={"date": today, "value": 10, "memo": "x", "content_id": "nope"})
    check("POST /api/data (없는 content_id → 422)", r.status_code == 422)
    r = client.post("/api/data", json={"date": "2999-01-01", "value": 10, "memo": "x"})
    check("POST /api/data (미래 날짜 → 422)", r.status_code == 422)
    r = client.post("/api/data", json={"date": today, "value": 0, "memo": "x"})
    check("POST /api/data (0분 → 422)", r.status_code == 422)

    r = client.put(f"/api/data/{rid}", json={"date": today, "value": 25, "memo": "시간 수정"})
    check("PUT /api/data/{id}", r.status_code == 200 and r.json()["value"] == 25)
    r = client.put("/api/data/none", json={"date": today, "value": 25, "memo": "x"})
    check("PUT /api/data/{없는 id} → 404", r.status_code == 404)

    r = client.get("/api/data")
    check("GET /api/data", r.status_code == 200 and len(r.json()) == 1)

    r = client.put("/api/profile", json={"age_band": "18+", "level": "L4", "goals": "영어 소설 읽기", "focus_skill": "reading", "daily_minutes": 30})
    check("PUT /api/profile", r.status_code == 200 and r.json()["level"] == "L4", str(r.json())[:120])
    r = client.put("/api/profile", json={"goals": None})
    check("PUT /api/profile (null로 비우기)", r.status_code == 200 and r.json()["goals"] is None and r.json()["level"] == "L4")
    client.put("/api/profile", json={"goals": "영어 소설 읽기"})

    r = client.get("/api/catalog", params={"age_band": "7-12", "skill": "reading"})
    check("GET /api/catalog (필터)", r.status_code == 200 and r.json()["count"] > 0)
    r = client.get("/api/catalog/ted-ed")
    check("GET /api/catalog/{id}", r.status_code == 200 and r.json()["title"] == "TED-Ed")

    r = client.get("/api/recommendations", params={"skill": "reading"})
    body = r.json()
    check("GET /api/recommendations", r.status_code == 200 and body["profile_ready"] and len(body["items"]) > 0,
          str([c["id"] for c in body.get("items", [])]))
    check("추천 카드: 성인 대상 + 이유", all("18+" in c["age_bands"] and c["reasons"] for c in body["items"]))

    # 채팅 (로컬 모드) — 의도별
    r = client.post("/api/chat", json={"message": "소설 읽기용 리딩 자료 추천해줘"})
    body = r.json()
    check("POST /api/chat (추천, 로컬)", r.status_code == 200 and body["mode"] == "local" and body["intent"] == "recommend"
          and body["recommendations"] and guardrails.AI_LABEL in body["reply"], body["reply"][:80])
    cid = body["conversation_id"]

    r = client.post("/api/chat", json={
        "message": "내 레벨 확인해줘", "conversation_id": cid,
        "history": [{"role": "user", "content": "소설 읽기용 리딩 자료 추천해줘"}, {"role": "assistant", "content": body["reply"]}],
    })
    check("POST /api/chat (레벨 체크리스트)", r.status_code == 200 and r.json()["intent"] == "placement" and "L6" in r.json()["reply"])

    r = client.post("/api/chat", json={"message": "요즘 내 학습은 어때?", "conversation_id": cid})
    check("POST /api/chat (진도 점검)", r.status_code == 200 and "분" in r.json()["reply"])

    r = client.post("/api/chat", json={"message": "아이가 ADHD인지 진단해 주세요"})
    check("POST /api/chat (범위 밖 → 가드레일)", r.status_code == 200 and r.json()["mode"] == "guardrail"
          and not r.json()["recommendations"])

    r = client.get(f"/api/conversations/{cid}")
    msgs = r.json().get("messages", [])
    check("대화 자동 저장 (3턴 = 6메시지 + 카드 보존)", r.status_code == 200 and len(msgs) == 6
          and msgs[1].get("recommendations"), f"{len(msgs)}개")

    r = client.post("/api/conversations", json={"title": "수동 저장", "messages": [{"role": "user", "content": "안녕"}]})
    check("POST /api/conversations", r.status_code == 201)
    r = client.get("/api/conversations")
    check("GET /api/conversations", r.status_code == 200 and len(r.json()) >= 2)

    r = client.delete(f"/api/data/{rid}")
    check("DELETE /api/data/{id}", r.status_code == 200)
    r = client.delete(f"/api/conversations/{cid}")
    check("DELETE /api/conversations/{id}", r.status_code == 200)
    r = client.delete(f"/api/conversations/{cid}")
    check("DELETE 반복 → 404", r.status_code == 404)

    r = client.post("/api/chat", json={"message": ""})
    check("POST /api/chat (빈 메시지 → 422)", r.status_code == 422)

    llm_failure_tests()
    openrouter_tests()

    r = client.get("/")
    check("GET / (frontend)", r.status_code == 200 and "Compass" in r.text)
    r = client.get("/app.js")
    check("GET /app.js", r.status_code == 200)


def llm_failure_tests() -> None:
    """API 비용 없이, 가짜 제공자로 크레딧 부족 등 계정 오류 처리를 검증한다."""
    from services import llm

    class FakeExc(Exception):
        body = {"type": "error", "error": {"type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API."}}

    detail = llm.error_detail(FakeExc())
    check("error_detail: 본문 메시지만 추출", detail.startswith("Your credit balance"))
    check("is_billing_error: 크레딧 부족 감지", llm.is_billing_error(detail))
    check("is_tool_error: 크레딧 오류는 도구 오류 아님", not llm.is_tool_error(detail))

    class BrokeProvider:
        name, model, calls = "claude", "fake-model", 0

        def chat(self, system, messages, web_search):
            BrokeProvider.calls += 1
            raise llm.LLMError("Anthropic 계정의 크레딧이 부족해 Claude를 호출하지 못했어요.", account_issue=True)

    saved = (llm._provider, llm._resolved)
    llm._provider, llm._resolved = BrokeProvider(), True
    try:
        r = client.post("/api/chat", json={"message": "리딩 자료 추천해줘"})
        body = r.json()
        check("크레딧 부족 → 로컬 응답으로 폴백", r.status_code == 200 and body["mode"] == "local"
              and body["recommendations"] and "크레딧" in " ".join(body["warnings"]), str(body["warnings"]))
        r = client.post("/api/chat", json={"message": "듣기 자료 추천해줘"})
        check("일시 중단 중엔 API 재호출 안 함", BrokeProvider.calls == 1 and r.json()["mode"] == "local",
              f"calls={BrokeProvider.calls}")
        h = client.get("/api/health").json()
        check("health: 일시 중단 사유 노출", bool(h["llm"]["paused_reason"]))
    finally:
        llm._provider, llm._resolved = saved
        llm.pause("", 0)
        llm.paused_reason()


def openrouter_tests() -> None:
    """OpenRouter 제공자 — 선택 로직·응답 파싱·오류 매핑 (가짜 클라이언트, 네트워크 없음)."""
    from types import SimpleNamespace

    import httpx
    import openai

    import config
    from services import llm
    from services.llm.openrouter_provider import OpenRouterProvider, parse_response

    # auto 모드: OpenRouter 키가 있으면 다른 키보다 우선
    saved_cfg = (config.LLM_PROVIDER, config.OPENROUTER_API_KEY, config.ANTHROPIC_API_KEY)
    try:
        config.LLM_PROVIDER, config.OPENROUTER_API_KEY, config.ANTHROPIC_API_KEY = "auto", "sk-or-test", "sk-ant-test"
        p = llm._build()
        check("auto: OpenRouter 키 우선 선택", isinstance(p, OpenRouterProvider) and p.model == config.OPENROUTER_MODEL,
              type(p).__name__)
        check("OpenRouter base_url", str(p.client.base_url).startswith("https://openrouter.ai/api/v1"))
    finally:
        config.LLM_PROVIDER, config.OPENROUTER_API_KEY, config.ANTHROPIC_API_KEY = saved_cfg

    # 응답 파싱: 중첩 url_citation 형식 + 중복 제거
    ann = {"type": "url_citation", "url_citation": {"url": "https://www.bbc.co.uk/learningenglish", "title": "BBC"}}
    resp = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content="추천입니다", annotations=[ann, ann]))])
    out = parse_response(resp, True, [])
    check("parse_response: 텍스트·출처", out.text == "추천입니다" and out.sources == [{"url": ann["url_citation"]["url"], "title": "BBC"}])
    try:
        parse_response(SimpleNamespace(choices=[]), False, [])
        check("parse_response: 빈 choices → LLMError", False)
    except llm.LLMError:
        check("parse_response: 빈 choices → LLMError", True)

    # 402(크레딧 부족) → 계정 오류
    provider = OpenRouterProvider("sk-or-test", "anthropic/claude-haiku-5.5", "https://openrouter.ai/api/v1")
    sent: dict = {}

    def broke(**kwargs):
        sent.update(kwargs)
        req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        raise openai.APIStatusError(
            "Insufficient credits", response=httpx.Response(402, request=req),
            body={"error": {"message": "Insufficient credits", "code": 402}},
        )

    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=broke)))
    try:
        provider.chat("sys", [{"role": "user", "content": "hi"}], web_search=True)
        check("402 → 크레딧 부족 계정 오류", False)
    except llm.LLMError as exc:
        check("402 → 크레딧 부족 계정 오류", exc.account_issue and "크레딧" in str(exc), str(exc))
    check("요청: web 플러그인 + system 메시지 + reasoning",
          sent["extra_body"]["plugins"][0]["id"] == "web" and sent["messages"][0]["role"] == "system"
          and "reasoning" in sent["extra_body"])


if __name__ == "__main__":
    unit_tests()
    api_tests()
    print(f"\nAll {passed} smoke tests passed.")
