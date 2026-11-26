"""Compass — 전 연령 영어 학습 콘텐츠 추천 AI 에이전트

로컬 실행:  ./run.sh            (또는 cd backend && python main.py)
배포:       Vercel (vercel.json, @vercel/python) — 프론트엔드 정적 파일도 같은 앱이 서빙
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from routers import catalog as catalog_router
from routers import chat as chat_router
from routers import conversations as conversations_router
from routers import data as data_router
from routers import profile as profile_router
from services import catalog, llm, store

app = FastAPI(
    title="Compass API",
    description=(
        "전 연령(3세~성인) 영어 학습 콘텐츠 추천 AI — 큐레이션 카탈로그 RAG + LLM(Claude/OpenAI) + 웹 검색. "
        "API 키가 없으면 카탈로그 규칙 기반으로 동작합니다."
    ),
    version=config.APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router.router)
app.include_router(conversations_router.router)
app.include_router(chat_router.router)
app.include_router(profile_router.router)
app.include_router(catalog_router.router)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    # 예기치 못한 오류도 프론트가 보여 줄 수 있는 JSON으로 (스택은 서버 로그에만)
    print(f"[compass] 처리되지 않은 오류: {type(exc).__name__}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "ok": True,
        "service": "compass",
        "version": config.APP_VERSION,
        "llm": llm.status(),
        "store": store.backend(),
        "catalog_items": len(catalog.items()),
    }


# API 라우트가 우선 매칭되고, 그 외 경로는 프론트엔드(정적)로 서빙
app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    print(f"Compass → http://{config.HOST}:{config.PORT}  (Swagger: /docs)")
    print(f"  LLM: {llm.status()['provider']} · 저장소: {store.backend()} · 카탈로그 {len(catalog.items())}개")
    uvicorn.run(
        "main:app", host=config.HOST, port=config.PORT, reload=True,
        app_dir=config.BACKEND_DIR, reload_dirs=[config.BACKEND_DIR, config.FRONTEND_DIR],
    )
