"""Compass — 전 연령 영어 학습 콘텐츠 추천 AI

로컬 실행:  cd backend && uvicorn main:app --reload
배포:       Vercel (vercel.json, @vercel/python) — 프론트엔드 정적 파일도 같은 앱이 서빙
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import ALLOWED_ORIGINS, FRONTEND_DIR
from routers import chat as chat_router
from routers import conversations as conversations_router
from routers import data as data_router
from routers import profile as profile_router

app = FastAPI(
    title="Compass API",
    description="전 연령 영어 학습 콘텐츠 추천 AI — 지식 + 웹 검색 기반 추천",
    version="0.1.0",
)

if ALLOWED_ORIGINS == ["*"]:
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(data_router.router)
app.include_router(conversations_router.router)
app.include_router(chat_router.router)
app.include_router(profile_router.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "service": "compass"}


# API 라우트가 우선 매칭되고, 그 외 경로는 프론트엔드(정적)로 서빙
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
