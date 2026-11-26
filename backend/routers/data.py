"""학습 기록 CRUD + 요약 (시계열 데이터)."""
from fastapi import APIRouter, HTTPException

from models.schemas import RecordIn
from services import catalog, store
from services.analysis import build_summary

router = APIRouter(prefix="/api/data", tags=["data"])


def _validated(rec: RecordIn) -> dict:
    body = rec.model_dump(exclude_none=True)
    if body.get("content_id") and not catalog.get(body["content_id"]):
        raise HTTPException(422, "존재하지 않는 카탈로그 콘텐츠입니다")
    return body


@router.post("", status_code=201)
def create_record(rec: RecordIn):
    body = _validated(rec)
    rid = store.add_record(body)
    return store.get_record(rid) or {"id": rid, **body}


@router.get("")
def list_records(limit: int = 500):
    return store.list_records()[: max(1, min(limit, 5000))]


@router.get("/summary")
def summary():
    """데이터 요약 — 프롬프트 주입용 + UI 요약 화면용."""
    return build_summary(store.list_records(), store.get_profile())


@router.put("/{rid}")
def update_record(rid: str, rec: RecordIn):
    body = _validated(rec)
    if not store.update_record(rid, body):
        raise HTTPException(404, "존재하지 않는 기록입니다")
    return store.get_record(rid)


@router.delete("/{rid}")
def delete_record(rid: str):
    if not store.delete_record(rid):
        raise HTTPException(404, "존재하지 않는 기록입니다")
    return {"ok": True}
